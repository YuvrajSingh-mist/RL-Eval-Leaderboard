import gradio as gr
import requests
import time
import json
from datetime import datetime
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")

def submit_script(file, env_id, algorithm, user_id):
    if not file:
        return "⚠️ Please upload a Python script"
    
    try:
        files = {'file': (file.name, open(file.name, 'rb'), 'text/plain')}
        data = {
            'env_id': env_id,
            'algorithm': algorithm,
            'user_id': user_id or "anonymous"
        }
        
        response = requests.post(f"{API_URL}/api/submit/", files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            return f"""
            ✅ Submission queued! ID: {result['id']}
            • Environment: {result['env_id']}
            • Algorithm: {result['algorithm']}
            Check results in 2-5 minutes
            """
        else:
            error_detail = response.json().get('detail', 'Unknown error')
            return f"❌ Error {response.status_code}: {error_detail}"
            
    except Exception as e:
        return f"❌ Connection error: {str(e)}"

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
        return "🔍 Please enter a submission ID", "N/A"
    
    try:
        response = requests.get(f"{API_URL}/api/results/{submission_id}")
        
        if response.status_code != 200:
            return f"❌ Error {response.status_code}: {response.json().get('detail', 'Unknown error')}", "N/A"
        
        result = response.json()
        status_map = {
            "pending": ("⏳", "Queued for evaluation"),
            "processing": ("⚙️", "Currently evaluating"),
            "completed": ("✅", f"Score: {result['score']:.2f}"),
            "failed": ("❌", f"Failed: {result.get('error', 'Unknown error')}")
        }
        
        emoji, status = status_map.get(result['status'], ("❓", "Unknown status"))
        return f"{emoji} {status}", result.get('score', 'N/A')
    except Exception as e:
        return f"❌ Connection error: {str(e)}", "N/A"

# Environment configuration
ENVIRONMENTS = [
    "CartPole-v1", "LunarLander-v2", 
    "MountainCar-v0", "Acrobot-v1"
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
                score_display = gr.Number(label="Final Score", interactive=False)
                status_output = gr.Textbox(label="Evaluation Status", lines=3)
        
        submit_btn.click(
            fn=submit_script,
            inputs=[script_upload, env_dropdown, algorithm, user_id],
            outputs=[status_box]
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
        check_btn.click(
            fn=check_status,
            inputs=id_input,
            outputs=[status_box, score_display]
        )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",  # Critical: bind to all interfaces
        server_port=7860,       # Must match EXPOSE in Dockerfile
        show_api=False,
        debug=True
    )
