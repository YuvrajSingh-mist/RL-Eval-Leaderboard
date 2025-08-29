# from app.core.docker import logger
import gradio as gr
import requests
import time
import json
from datetime import datetime, timezone
import os
import logging
API_URL = os.getenv("API_URL", "http://localhost:8000")
PORT = int(os.getenv("PORT", "7860"))
# Public site URL for SEO; uses environment variable or defaults to Render URL
SITE_URL = os.getenv("PUBLIC_BASE_URL", "https://rl-eval-leaderboard.onrender.com").rstrip("/")
GITHUB_URL = "https://github.com/YuvrajSingh-mist/RL-Eval-Leaderboard"
_last_submission_id = None
logger = logging.getLogger(__name__)


    
def submit_script(file, env_id, algorithm, user_id):
    # Single-file only
    if not file:
        return "⚠️ Please upload a Python script (.py)"

    try:
        import uuid as _uuid
        client_id = str(_uuid.uuid4())

        # Single-file path only
        if not str(file.name).lower().endswith('.py'):
            return "⚠️ Only .py files are accepted"
        submit_files = {'file': (file.name, open(file.name, 'rb'), 'text/plain')}
        data = {
            'env_id': env_id,
            'algorithm': algorithm,
            'user_id': user_id or "anonymous",
            'client_id': client_id
        }

        response = requests.post(f"{API_URL}/api/submit/", files=submit_files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            # Persist locally for Check Status tab (until refresh)
            global _last_submission_id
            _last_submission_id = result.get('id', client_id)
            sid = _last_submission_id
            html = f"""
            <div class=\"status-box success\">
              <div class=\"status-header\">
                <span>✅</span>
                <span>Submission queued</span>
                <span class=\"status-pill\">Waiting to evaluate</span>
              </div>
              <div class=\"status-id\">
                <b>ID:</b> <code>{sid}</code>
                <button class=\"copy-btn\" onclick=\"navigator.clipboard.writeText('{sid}'); this.innerText='Copied'; setTimeout(()=>{{ this.innerText='Copy ID'; }}, 1600);\">Copy ID</button>
              </div>
              <div class=\"status-kv\">
                <div class=\"label\">Environment</div><div class=\"value\">{result['env_id']}</div>
                <div class=\"label\">Algorithm</div><div class=\"value\">{result['algorithm']}</div>
              </div>
              <div class=\"status-foot\"><b>Keep your Submission ID safe!</b> You'll need it in the <i>Check Status</i> tab to view progress and error logs.</div>
            </div>
            """
            return html
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            return f"❌ Error {response.status_code}: {error_detail}"
            
    except Exception as e:
        return f"❌ Error: {str(e)}"

def get_leaderboard(env_id, id_query, user_query, algorithm_query, score_min, score_max, sort_order):
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
        if user_query:
            params["user"] = str(user_query).strip()
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

            rank_val = e.get("rank", None)
            medal_field = str(e.get("medal", "" ) or "").lower()
            medal_icon = ""
            if medal_field == "gold":
                medal_icon = "🥇 "
            elif medal_field == "silver":
                medal_icon = "🥈 "
            elif medal_field == "bronze":
                medal_icon = "🥉 "
            rank_str = f"{medal_icon}{rank_val}" if rank_val is not None else "-"

            table.append([
                rank_str,
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
            score_text = f"{score_num:.2f}" if score_num is not None else "N/A"
            return status_html, score_text
        elif status == 'processing':
            return f"⚙️ Currently evaluating\nID: {_escape(submission_id)}", "In progress"
        elif status == 'pending':
            return f"⏳ Queued for evaluation\nID: {_escape(submission_id)}", "In progress"
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
            return status_html, "Failed"
        else:
            return f"❓ Unknown status\nID: {_escape(submission_id)}", "Unknown"
    except Exception as e:
        return f"❌ Error: {str(e)}", None

with gr.Blocks(title="SimpleRL Leaderboard", css="""
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
/* Cute GitHub button (top-right) */
.gh-btn {
  position: fixed; top: 12px; right: 12px; z-index: 9999;
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-radius: 999px;
  background: linear-gradient(180deg, #24292e, #1f2328);
  border: 1px solid rgba(255,255,255,.08);
  box-shadow: 0 8px 20px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
  color: #fff; text-decoration: none; font-weight: 600;
}
.gh-btn:hover { filter: brightness(1.08); transform: translateY(-1px); }
.gh-btn:active { transform: translateY(0); }
.gh-ico { font-size: 1.1rem; line-height: 1; }
.gh-text { font-size: .95rem; }
@media (max-width: 520px) { .gh-text { display: none; } }
""") as demo:
    gr.Markdown("# 🏆 SimpleRL Leaderboard")
    # Inject SEO meta tags into <head>
    gr.HTML(
        """
        <script>
        (function(){
          try {
            var head = document.head || document.getElementsByTagName('head')[0];
            function setMeta(attr, name, content){
              var selector = attr + '="' + name + '"';
              var el = head.querySelector('meta[' + selector + ']');
              if (!el) { el = document.createElement('meta'); el.setAttribute(attr, name); head.appendChild(el); }
              el.setAttribute('content', content);
            }
            function setLink(rel, href){
              var el = head.querySelector('link[rel="' + rel + '"]');
              if (!el) { el = document.createElement('link'); el.setAttribute('rel', rel); head.appendChild(el); }
              el.setAttribute('href', href);
            }
            var url = '%s';
            var title = 'SimpleRL Leaderboard – Evaluate and Rank RL Agents';
            var desc = 'Submit Python RL agents for automatic evaluation on Gym environments. View scores and rankings on the live leaderboard.';
            document.title = title;
            setMeta('name', 'description', desc);
            setMeta('name', 'robots', 'index,follow');
            setMeta('property', 'og:type', 'website');
            setMeta('property', 'og:title', title);
            setMeta('property', 'og:description', desc);
            setMeta('property', 'og:url', url + '/');
            setMeta('name', 'twitter:card', 'summary');
            setMeta('name', 'twitter:title', title);
            setMeta('name', 'twitter:description', desc);
            setLink('canonical', url + '/');
          } catch(e) { /* noop */ }
        })();
        </script>
        """ % (SITE_URL)
    )
    gr.HTML(f"""
    <a class=\"gh-btn\" href=\"{GITHUB_URL}\" target=\"_blank\" rel=\"noopener\" aria-label=\"View project on GitHub\"> 
      <span class=\"gh-ico\">🐙</span>
      <span class=\"gh-text\">GitHub</span>
    </a>
    """)
    
    # About / README tab
    def _load_readme_text():
        try:
            here = os.path.dirname(__file__)
            readme_path = os.path.abspath(os.path.join(here, "..", "README.md"))
            if os.path.exists(readme_path):
                with open(readme_path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception:
            logger.exception("Failed to load README.md")
        return None
    _README_TEXT = _load_readme_text()

    with gr.Tab("About"):
        gr.Markdown(
            """
            ### About
            **SimpleRL Leaderboard** lets you submit a single-file Python RL agent for automatic evaluation on popular Gym/Gymnasium environments. Your results appear on the Leaderboard, and you can track progress using your Submission ID.

            ### How to submit
            - **1. Choose environment**: Pick a Gym environment from the dropdown (use Refresh Envs if empty).
            - **2. Algorithm name**: Enter a short label for your method (e.g., "DQN").
            - **3. Optional user ID**: Any string to identify you or your team.
            - **4. Upload script**: Provide a single `.py` file containing your agent implementation.
            - **5. Submit**: Click "Submit for Evaluation". Copy the shown **Submission ID**.
            - **6. Check progress**: Use the ID in the "Check Status" tab or wait for the Leaderboard to update.

            Tip: See the example agents at `example_agents/dqn.py` and `example_agents/q_learning.py` in this repository.

            ### Tabs guide
            - **Submit Agent**: Upload a `.py` file, choose environment and algorithm name, then submit. Keep the Submission ID to monitor results or debug failures.
            - **Leaderboard**: Browse scores for the selected environment. Use filters (ID, User, Algorithm, score range) and sorting. The table auto-refreshes periodically; you can also click Refresh.
            - **Check Status**: Paste your Submission ID to see whether it is queued, processing, completed (with final score), or failed (with error details).
            """
        )
        if _README_TEXT:
            with gr.Accordion("Full Project README", open=False):
                gr.Markdown(_README_TEXT)
    
    with gr.Tab("Submit Agent"):
        with gr.Row():
            with gr.Column():
                user_id = gr.Textbox(label="Your ID (optional)", placeholder="e.g., team-rocket")
                env_dropdown = gr.Dropdown(
                    label="Gym Environment", 
                    choices=[], 
                    value=None
                )
                env_reload_btn = gr.Button("Refresh Envs", size="sm")
                algorithm = gr.Textbox(label="Algorithm Name", value="Custom DQN")
                script_upload = gr.File(label="Script (.py)", file_types=['.py'])
                submit_btn = gr.Button("Submit for Evaluation", variant="primary", elem_id="submit-eval-btn")
            
            with gr.Column():
                status_box = gr.HTML(value="<div class='status-box'>Submit your agent to start!<br/><small><b>Note:</b> Only a single-file Python implementation is accepted. Keep your <b>Submission ID</b> safe to check status and error logs later.</small></div>")
        
        submit_btn.click(
            fn=submit_script,
            inputs=[script_upload, env_dropdown, algorithm, user_id],
            outputs=[status_box]
        )
        
        
    
    with gr.Tab("Leaderboard"):
        with gr.Row():
            env_selector = gr.Dropdown(
                label="Environment", 
                choices=[], 
                value=None
            )
            envs_refresh_btn = gr.Button("Refresh Envs", elem_id="refresh-envs-btn")
            leaderboard_btn = gr.Button("Refresh Leaderboard", variant="primary")

        with gr.Accordion("Filters", open=False):
            with gr.Row():
                id_filter = gr.Textbox(label="Submission ID contains", placeholder="UUID or part")
                user_filter = gr.Textbox(label="User contains", placeholder="e.g., alice")
                algorithm_filter = gr.Textbox(label="Algorithm contains", placeholder="e.g., DQN")
            with gr.Row():
                score_min = gr.Number(label="Min score", value=-1000)
                score_max = gr.Number(label="Max score", value=1000)
                sort_order = gr.Dropdown(
                    label="Sort order",
                    choices=["Score (desc)", "Date (newest)", "Date (oldest)"],
                    value="Score (desc)"
                )
            # Date filters removed per request

        leaderboard = gr.Dataframe(
            headers=["Rank", "Submission ID", "User", "Score", "Algorithm", "Date (in UTC)"],
            datatype=["str", "str", "str", "number", "str", "str"],
            col_count=(6, "fixed"),
            elem_id="leaderboard-table"
        )

        # Quick range removed per request

        leaderboard_btn.click(
            fn=get_leaderboard,
            inputs=[env_selector, id_filter, user_filter, algorithm_filter, score_min, score_max, sort_order],
            outputs=leaderboard
        )

        # Fetch environments from backend endpoint
        def fetch_envs():
            try:
                res = requests.get(f"{API_URL}/api/leaderboard/environments")
                if res.status_code == 200:
                    envs = res.json().get("envs", [])
                    if envs:
                        return gr.update(choices=envs, value=envs[0])
                    else:
                        logger.error("Environments endpoint returned empty list")
                else:
                    logger.error(f"Failed to fetch environments: status {res.status_code}")
            except Exception:
                logger.exception("Error fetching environments")
            defaults = [
                "CartPole-v1","MountainCar-v0","Acrobot-v1","Pendulum-v1",
                "FrozenLake-v1","LunarLander-v2","LunarLanderContinuous-v2"
            ]
            return gr.update(choices=defaults, value=defaults[0])

        def fetch_envs_both():
            upd = fetch_envs()
            return upd, upd

        envs_refresh_btn.click(fn=fetch_envs, inputs=None, outputs=env_selector)
        env_reload_btn.click(fn=fetch_envs, inputs=None, outputs=env_dropdown)

        # Inject JS for auto-refresh every 30 seconds and default to Leaderboard
        gr.HTML("""
        <style>
        #leaderboard-table table { font-size: 0.95rem; }
        #leaderboard-table thead th { position: sticky; top: 0; background: #161616; color: #f3f3f3; }
        #leaderboard-table td:nth-child(4) { text-align: right; font-variant-numeric: tabular-nums; }
        #leaderboard-table td, #leaderboard-table th { padding: 8px 12px; }
        /* Make Refresh Envs button align and size similarly to primary button */
        #refresh-envs-btn button, #refresh-envs-btn {
          padding: 8px 12px !important;
          height: 40px !important;
          line-height: 24px !important;
          margin-left: 8px !important;
        }
        /* Orange accent for Submit button */
        #submit-eval-btn button, #submit-eval-btn { 
          background: linear-gradient(180deg, #ff8c1a, #e67600) !important; 
          border: 1px solid #cc6a00 !important; color: #1b1b1b !important; 
        }
        #submit-eval-btn:hover button, #submit-eval-btn:hover { 
          background: linear-gradient(180deg, #ffa64d, #ff8c1a) !important; 
        }
        </style>
        <script>
        (function(){
          const API = (window.API_URL || '%s');
          async function ensureVisitorToken(){
            try {
              // Try cookie-based flow first
              const r = await fetch(API + '/api/visitor/token', {credentials: 'include'});
              let tok = null;
              try { tok = (await r.json()).token; } catch(e) {}
              if (!tok) {
                // Fallback: persist in localStorage
                tok = window.localStorage.getItem('visitor_token');
                if (!tok) {
                  // If backend didn’t return JSON (due to CORS), issue a client-side token request not possible.
                  // Keep null; backend will treat missing cookie but accept header if present later.
                }
              } else {
                try { window.localStorage.setItem('visitor_token', tok); } catch(e) {}
              }
              // Fire a pixel; include header if we have a token (works even if third-party cookies blocked)
              fetch(API + '/api/visitor/pixel?t=' + Date.now(), {
                mode: 'no-cors',
                credentials: 'include',
                headers: tok ? { 'X-Visitor-Token': tok } : {}
              }).catch(()=>{});
            } catch (e) { /* noop */ }
          }
          window.addEventListener('load', ensureVisitorToken);
        })();
        setInterval(function() {
            const btn = Array.from(document.querySelectorAll("button"))
                .find(b => b.innerText.includes("Refresh Leaderboard"));
            if (btn) { btn.click(); }
        }, 30000);
        window.addEventListener('load', function(){
          const tab = Array.from(document.querySelectorAll('[role="tab"], .tabitem')).find(el => (el.innerText||'').includes('Leaderboard'));
          if (tab) { try { tab.click(); } catch(e){} }
        });
        </script>
        """ % (API_URL))

        # Populate environment dropdowns on load using backend discovery
        demo.load(fn=fetch_envs_both, inputs=None, outputs=[env_selector, env_dropdown])
    
    with gr.Tab("Check Status"):
        status_box_cs = gr.HTML(value="<div class='status-box'>Enter a submission ID and click Check.</div>")
        # hint = gr.Markdown("Enter a submission ID and click Check.")
        id_input = gr.Textbox(label="Submission ID", placeholder="Enter your submission ID")
        check_btn = gr.Button("Check Status")
       
        score_display_cs = gr.Number(label="Final Score", interactive=False)
        check_btn.click(
            fn=check_status,
            inputs=[id_input],
            outputs=[status_box_cs, score_display_cs]
        )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=PORT,
        show_api=False,
        debug=True
    )