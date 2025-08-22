import gradio as gr
import requests
import time
import json
from datetime import datetime, timezone
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")
_last_submission_id = None

def submit_script(primary_file, extra_files, main_filename, env_id, algorithm, user_id):
    # Backward-compatible UX: user can provide either one file or multiple
    if not primary_file and not (extra_files and len(extra_files) > 0):
        return "⚠️ Please upload at least one Python script", ""

    try:
        import uuid as _uuid
        client_id = str(_uuid.uuid4())

        # Decide whether to send multiple files or single
        submit_files = []
        if extra_files and len(extra_files) > 0:
            # Multi-part: include extra_files and primary_file if present
            # Gradio's File component gives a tempfile path per file
            def _as_tuple(f):
                # requests expects (filename, fileobj, mimetype)
                return ('files', (f.name, open(f.name, 'rb'), 'text/plain'))
            for f in (extra_files or []):
                submit_files.append(_as_tuple(f))
            if primary_file:
                submit_files.append(_as_tuple(primary_file))
            # Require main file name when multiple files are uploaded
            mf_name = (main_filename or '').strip()
            if not mf_name:
                return "⚠️ Please specify the main .py filename for multi-file submissions", ""
            # Validate at least one .py present and main_file endswith .py
            names = [getattr(f, 'orig_name', None) or os.path.basename(f.name) for f in (extra_files or [])]
            if primary_file:
                names.append(getattr(primary_file, 'orig_name', None) or os.path.basename(primary_file.name))
            if not any(str(n).lower().endswith('.py') for n in names):
                return "⚠️ Multi-file upload must include at least one .py file", ""
            if not mf_name.lower().endswith('.py'):
                return "⚠️ main_file must end with .py", ""
            data = {
                'env_id': env_id,
                'algorithm': algorithm,
                'user_id': user_id or "anonymous",
                'client_id': client_id,
                'main_file': mf_name
            }
        else:
            # Single-file path
            files = {'file': (primary_file.name, open(primary_file.name, 'rb'), 'text/plain')}
            data = {
                'env_id': env_id,
                'algorithm': algorithm,
                'user_id': user_id or "anonymous",
                'client_id': client_id
            }
            submit_files = files

        response = requests.post(f"{API_URL}/api/submit/", files=submit_files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            # Persist locally for Check Status tab (until refresh)
            global _last_submission_id
            _last_submission_id = result.get('id', client_id)
            sid = _last_submission_id
            html = f"""
            <div class="status-box success">
              <div class="status-header">
                <span>✅</span>
                <span>Submission queued</span>
                <span class="status-pill">Waiting to evaluate</span>
              </div>
              <div class="status-id">
                <b>ID:</b> <code>{sid}</code>
                <button class="copy-btn" onclick="navigator.clipboard.writeText('{sid}'); this.innerText='Copied'; setTimeout(()=>{{ this.innerText='Copy ID'; }}, 1600);">Copy ID</button>
              </div>
              <div class="status-kv">
                <div class="label">Environment</div><div class="value">{result['env_id']}</div>
                <div class="label">Algorithm</div><div class="value">{result['algorithm']}</div>
              </div>
              <div class="status-foot">Use this ID in the <i>Check Status</i> tab.</div>
            </div>
            """
            return html, sid
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            return f"❌ Error {response.status_code}: {error_detail}", ""
            
    except Exception as e:
        return f"❌ Error: {str(e)}", ""

def get_leaderboard(env_id, id_query, algorithm_query, score_min, score_max, sort_order):
    """Fetch leaderboard from API using server-side filters/sorting and render rows."""
    try:
        # Map UI sort order to API sort values
        sort_map = {
            "Date (newest)": "date_desc",
            "Date (oldest)": "date_asc",
            "Score (desc)": "score_desc",
        }
        sort = sort_map.get((sort_order or "Score (desc)").strip(), "score_desc")

        def _date_to_str(d):
            if d is None:
                return None
            # Accept either a date object or a string in YYYY-MM-DD
            try:
                return d.strftime("%Y-%m-%d")
            except Exception:
                pass
            try:
                ds = str(d).strip()[:10]
                # strict validation
                _ = datetime.strptime(ds, "%Y-%m-%d")
                return ds
            except Exception:
                return None

        params = {"env_id": env_id, "limit": 200, "sort": sort}
        if id_query:
            params["id_query"] = str(id_query).strip()
        if algorithm_query:
            params["algorithm"] = str(algorithm_query).strip()
        if score_min is not None and str(score_min) != "":
            try:
                params["score_min"] = float(score_min)
            except Exception:
                pass
        if score_max is not None and str(score_max) != "":
            try:
                params["score_max"] = float(score_max)
            except Exception:
                pass
        # Dates removed per request

        response = requests.get(f"{API_URL}/api/leaderboard/", params=params)
        if response.status_code != 200:
            return [["Error", "-", f"Failed: {response.status_code}", None, "-", "-"]]

        entries = response.json() or []
        if not entries:
            return [[None, "-", "No submissions yet", None, "-", "-"]]

        # Build table rows as returned by server (already sorted/ranked)
        table = []
        for e in entries:
            try:
                created_at = e.get("created_at")
                dtv = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None) if isinstance(created_at, str) else None
            except Exception:
                dtv = None
            pretty_dt = dtv.strftime("%Y-%m-%d %H:%M") if dtv else "-"
            score_val = e.get("score")
            score_num = float(score_val) if isinstance(score_val, (int, float)) else None

            table.append([
                e.get("rank", None),
                e.get("id", ""),
                e.get("user_id", "Unknown"),
                score_num,
                e.get("algorithm", "Unknown"),
                pretty_dt,
            ])
        return table
    except Exception as e:
        return [["Error", "-", str(e), None, "-", "-"]]

def check_status(submission_id):
    """Check the status of a submission"""
    if not submission_id:
        # Use last submission id if user left input empty
        global _last_submission_id
        if _last_submission_id:
            submission_id = _last_submission_id
        else:
            return "🔍 Please enter a submission ID", "N/A"
    
    try:
        response = requests.get(f"{API_URL}/api/results/{submission_id}")
        
        if response.status_code != 200:
            return f"❌ Error {response.status_code}: {response.json().get('detail', 'Unknown error')}", None
        
        result = response.json()
        status = str(result.get('status', 'unknown'))
        score_val = result.get('score', None)
        score_num = None
        if isinstance(score_val, (int, float)):
            score_num = float(score_val)
        
        from html import escape as _escape
        if status == 'completed':
            status_html = f"✅ Completed\nID: {_escape(submission_id)}\nScore: {score_num:.2f}" if score_num is not None else f"✅ Completed\nID: {_escape(submission_id)}"
            return status_html, score_num
        elif status == 'processing':
            return f"⚙️ Currently evaluating\nID: {_escape(submission_id)}", None
        elif status == 'pending':
            return f"⏳ Queued for evaluation\nID: {_escape(submission_id)}", None
        elif status == 'failed':
            err = str(result.get('error', 'Unknown error'))
            status_html = f"""
<div class='status-box'>
  <div>❌ Failed</div>
  <div><b>ID:</b> <code>{_escape(submission_id)}</code></div>
  <div style='margin-top:8px'><b>Error:</b></div>
  <pre style='white-space:pre-wrap; background:#111; color:#eee; padding:8px; border-radius:4px'>{_escape(err)}</pre>
</div>
"""
            return status_html, None
        else:
            return f"❓ Unknown status\nID: {_escape(submission_id)}", None
    except Exception as e:
        return f"❌ Error: {str(e)}", None

# Environment configuration
ENVIRONMENTS = [
    "CartPole-v1", "LunarLander-v2", "LunarLanderContinuous-v2",
    "MountainCar-v0", "Acrobot-v1", "Pendulum-v1", "FrozenLake-v1"
]

with gr.Blocks(title="RL Leaderboard", css="""
.status-box {
  font-size: 1rem;
  background: linear-gradient(180deg, rgba(32,59,49,.5), rgba(17,32,27,.5));
  border: 1px solid #1a3d30;
  border-radius: 12px;
  padding: 16px 18px;
  color: #e8f5ef;
  box-shadow: 0 8px 24px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.05);
}
.status-box.success {
  border-color: rgba(43,217,138,.4);
  background: linear-gradient(180deg, rgba(19,54,41,.7), rgba(10,26,20,.7));
}
.status-header {
  display: flex; align-items: center; gap: 10px; margin-bottom: 6px; font-weight: 600;
}
.status-pill {
  background: rgba(43,217,138,.12);
  color: #2bd98a;
  border: 1px solid rgba(43,217,138,.35);
  padding: 2px 8px; border-radius: 999px; font-size: .85em;
}
.status-id { display: flex; align-items: center; gap: 8px; margin: 8px 0 12px 0; }
.status-id code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace;
  background: rgba(0,0,0,.35);
  padding: 6px 8px; border-radius: 6px; border: 1px solid rgba(255,255,255,.06);
}
.copy-btn {
  background: rgba(43,217,138,.15); color: #2bd98a; border: 1px solid rgba(43,217,138,.3);
  border-radius: 6px; padding: 6px 8px; cursor: pointer;
}
.copy-btn:hover { background: rgba(43,217,138,.25); }
.status-kv { display: grid; grid-template-columns: 120px 1fr; row-gap: 6px; column-gap: 10px; margin-bottom: 4px; }
.status-kv .label { color: #9ecfb6; }
.status-kv .value { color: #e8f5ef; font-weight: 500; }
.status-foot { margin-top: 10px; color: #9ecfb6; font-size: .95em; }
.status-box pre { white-space: pre-wrap; background: #111; color: #eee; padding: 8px; border-radius: 6px; border: 1px solid rgba(255,255,255,.06); }
""") as demo:
    gr.Markdown("# 🏆 Reinforcement Learning Leaderboard")
    
    with gr.Tab("Submit Agent"):
        with gr.Row():
            with gr.Column():
                user_id = gr.Textbox(label="Your ID (optional)", placeholder="e.g., team-rocket")
                env_dropdown = gr.Dropdown(
                    label="Gym Environment", 
                    choices=ENVIRONMENTS, 
                    value="CartPole-v1"
                )
                algorithm = gr.Textbox(label="Algorithm Name", value="Custom DQN")
                script_upload = gr.File(label="Main Script (.py)", file_types=['.py'])
                extra_uploads = gr.File(label="Additional Files (any)", file_count="multiple")
                main_file_name = gr.Textbox(label="Main file name (optional)", placeholder="e.g., main.py or submission.py")
                submit_btn = gr.Button("Submit for Evaluation", variant="primary")
            
            with gr.Column():
                status_box = gr.HTML(value="<div class='status-box'>Submit your agent to start!</div>")
                submission_id_box = gr.Textbox(label="Submission ID", interactive=False)
                try:
                    # Some versions support copy button
                    submission_id_box.show_copy_button = True
                except Exception:
                    pass
        
        submit_btn.click(
            fn=submit_script,
            inputs=[script_upload, extra_uploads, main_file_name, env_dropdown, algorithm, user_id],
            outputs=[status_box, submission_id_box]
        )
        
        
    
    with gr.Tab("Leaderboard"):
        with gr.Row():
            env_selector = gr.Dropdown(
                label="Environment", 
                choices=ENVIRONMENTS, 
                value="CartPole-v1"
            )
            leaderboard_btn = gr.Button("Refresh Leaderboard", variant="primary")

        with gr.Accordion("Filters", open=False):
            with gr.Row():
                id_filter = gr.Textbox(label="Submission ID contains", placeholder="UUID or part")
                algorithm_filter = gr.Textbox(label="Algorithm contains", placeholder="e.g., DQN")
            with gr.Row():
                score_min = gr.Number(label="Min score")
                score_max = gr.Number(label="Max score")
                sort_order = gr.Dropdown(
                    label="Sort order",
                    choices=["Score (desc)", "Date (newest)", "Date (oldest)"],
                    value="Score (desc)"
                )
            # Date filters removed per request

        leaderboard = gr.Dataframe(
            headers=["Rank", "Submission ID", "User", "Score", "Algorithm", "Date (UTC)"],
            datatype=["number", "str", "str", "number", "str", "str"],
            col_count=(6, "fixed"),
            elem_id="leaderboard-table"
        )

        # Quick range removed per request

        leaderboard_btn.click(
            fn=get_leaderboard,
            inputs=[env_selector, id_filter, algorithm_filter, score_min, score_max, sort_order],
            outputs=leaderboard
        )

        # Inject JS for auto-refresh every 30 seconds
        gr.HTML("""
        <style>
        #leaderboard-table table { font-size: 0.95rem; }
        #leaderboard-table thead th { position: sticky; top: 0; background: #161616; color: #f3f3f3; }
        #leaderboard-table td:nth-child(1),
        #leaderboard-table td:nth-child(4) { text-align: right; font-variant-numeric: tabular-nums; }
        #leaderboard-table td, #leaderboard-table th { padding: 8px 12px; }
        </style>
        <script>
        setInterval(function() {
            const btn = Array.from(document.querySelectorAll("button"))
                .find(b => b.innerText.includes("Refresh Leaderboard"));
            if (btn) { btn.click(); }
        }, 30000);
        </script>
        """)
    
    with gr.Tab("Check Status"):
        id_input = gr.Textbox(label="Submission ID", placeholder="Enter your submission ID")
        check_btn = gr.Button("Check Status")
        status_box_cs = gr.HTML(value="<div class='status-box'>Enter a submission ID and click Check.</div>")
        score_display_cs = gr.Number(label="Final Score", interactive=False)
        check_btn.click(
            fn=check_status,
            inputs=[id_input],
            outputs=[status_box_cs, score_display_cs]
        )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",  # Critical: bind to all interfaces
        server_port=7860,       # Must match EXPOSE in Dockerfile
        show_api=False,
        debug=True
    )
