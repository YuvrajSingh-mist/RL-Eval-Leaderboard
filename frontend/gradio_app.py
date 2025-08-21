import gradio as gr
import requests
import time
import json
from datetime import datetime
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")
_last_submission_id = None

def submit_script(file, env_id, algorithm, user_id):
    if not file:
        return "⚠️ Please upload a Python script", ""
    
    try:
        import uuid as _uuid
        # Generate client-side UUID so user can copy immediately without waiting for backend
        client_id = str(_uuid.uuid4())
        files = {'file': (file.name, open(file.name, 'rb'), 'text/plain')}
        data = {
            'env_id': env_id,
            'algorithm': algorithm,
            'user_id': user_id or "anonymous",
            'client_id': client_id
        }
        
        response = requests.post(f"{API_URL}/api/submit/", files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            # Persist locally for Check Status tab (until refresh)
            global _last_submission_id
            _last_submission_id = result.get('id', client_id)
            sid = _last_submission_id
            html = f"""
            <div class='status-box'>
              <div>✅ Submission queued!</div>
              <div><b>ID:</b> <code>{sid}</code></div>
              <div>• Environment: {result['env_id']}</div>
              <div>• Algorithm: {result['algorithm']}</div>
              <div>Use this ID in the <i>Check Status</i> tab.</div>
            </div>
            """
            return html, sid
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            return f"❌ Error {response.status_code}: {error_detail}", ""
            
    except Exception as e:
        return f"❌ Error: {str(e)}", ""

def get_leaderboard(env_id):
    """Get leaderboard from Redis (real-time sorting)"""
    try:
        response = requests.get(f"{API_URL}/api/leaderboard/", params={"env_id": env_id})
        
        if response.status_code != 200:
            return [["Error", "Failed to load leaderboard"]]
        
        entries = response.json()
        if not entries:
            return [["-", "No submissions yet", "-", "-", "-"]]
        
        return [
            [entry.get("rank", i+1), 
             entry["user_id"], 
             f"{entry['score']:.2f}", 
             entry["algorithm"], 
             datetime.fromisoformat(entry["created_at"]).strftime("%b %d")]
            for i, entry in enumerate(entries)
        ]
    except Exception as e:
        return [["Error", str(e), "-", "-", "-"]]

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

with gr.Blocks(title="RL Leaderboard", css=".status-box {font-size: 1.2em;}") as demo:
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
                script_upload = gr.File(label="Upload RL Script (.py)", file_types=['.py'])
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
            inputs=[script_upload, env_dropdown, algorithm, user_id],
            outputs=[status_box, submission_id_box]
        )
        
        
    
    with gr.Tab("Leaderboard"):
        with gr.Row():
            env_selector = gr.Dropdown(
                label="Environment", 
                choices=ENVIRONMENTS, 
                value="CartPole-v1"
            )
            leaderboard_btn = gr.Button("Refresh Leaderboard")
        leaderboard = gr.Dataframe(
            headers=["Rank", "User", "Score", "Algorithm", "Date"],
            datatype=["number", "str", "number", "str", "str"],
            col_count=(5, "fixed")
        )
        
        leaderboard_btn.click(
            fn=get_leaderboard,
            inputs=env_selector,
            outputs=leaderboard
        )

        # Inject JS for auto-refresh every 30 seconds
        gr.HTML("""
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
            inputs=id_input,
            outputs=[status_box_cs, score_display_cs]
        )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",  # Critical: bind to all interfaces
        server_port=7860,       # Must match EXPOSE in Dockerfile
        show_api=False,
        debug=True
    )
