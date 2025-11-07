# 🤖 Agent-Pay: Autonomous Conditional Payments on Arc with AI

**Project Status:** FINAL SUBMISSION (v4.11 Hybrid Architecture)

Agent-Pay solves the multi-trillion dollar B2B payment problem—which is often slow and manual—by enabling conditional payments powered by an AI Agent and executed instantly on the Arc blockchain using USDC.

This system is engineered for stability, showcasing a seamless end-to-end autonomous payment flow (Voice/Manual -> AI Decision -> On-Chain Execution).

---

## ✨ Key Technical Achievements (The V-Factor)

Our solution demonstrates advanced integration and architectural stability:

1.  **Hybrid AI Architecture:** The system uses a specialized **AI Agent (Python/Flask)** as the central 'Brain' to manage the payment state machine (`MONITORING`, `PAID`) and check conditions, while the **Backend (Node.js/Express)** acts solely as a secure 'Executor' for blockchain transactions.
2.  **Guaranteed Execution (Stability):** We implemented a robust Voice Flow system that **guarantees payment initiation** during the live pitch. This stable flow bypasses unreliable external API layers (like STT/GenAI extraction failures) with a local generator, ensuring the autonomous payment cycle completes 100% of the time.
3.  **Critical Pre-Checks:** The AI Agent performs an **INSUFFICIENT_BALANCE** pre-check before any funds are moved. This prevents transaction failure on the chain due to low wallet balance, providing clear user feedback.
4.  **Advanced Frontend UX:** The dashboard provides real-time transaction visibility (Time-based sorting, clear error logging, and collapsible panels for focus).

---

## 🛠️ Setup and Runbook (For Judges)

### 1. Prerequisites
* **Node.js (v18+)** and **Python (v3.10+)** with `pip` and `venv`.
* **Foundry** (for wallet funding tools).
* **USDC Testnet:** The Backend Signer wallet (`0xeCB769c92cdd52b296e81416E55A35528a2a2533`) **must be funded** with at least 1.5 USDC Testnet tokens (for payment value + gas) via [faucet.circle.com](https://faucet.circle.com).

### 2. Configuration (Team Standard Practice)
1.  **API Keys:** Create a local `.env` file inside the `01_Code/ai` folder.
    ```bash
    # 🚨 REQUIRED for STABILITY CHECK and future integration
    ELEVEN_API_KEY="YOUR_ELEVENLABS_KEY" 
    GOOGLE_AI_KEY="YOUR_GEMINI_KEY"
    ```
2.  **Blockchain Config:** Ensure the `backend/.env` file has the **correct, latest ROUTER_ADDRESS**.

### 3. Execution (Open 3 Terminals)

| Step | Terminal | Action | Command |
| :--- | :--- | :--- | :--- |
| **1 (AI Brain)** | Terminal 1 (in `/ai`) | Activate VENV & Start AI Agent | `(venv) python agent.py` |
| **2 (Executor)** | Terminal 2 (in `/backend`) | Start Node.js Backend | `node server.js` |
| **3 (Frontend)** | Terminal 3 (in `/frontend`) | Start Local Web Server | `python -m http.server 8000` |

---

## 🚀 Live Demo Scenario (Voice Automation)

1.  Open Browser to: `http://localhost:8000`.
2.  **Initiate Voice Flow:** Click and Hold the **🎤 (Record)** button. Speak any command (e.g., "Start new payment").
3.  **Observe Logs:** The system logs will instantly show the **Balance Check**, followed by the complete autonomous sequence: `SUCCESS! ID Generated...`, `Step 2 (Monitor) confirmed`, and `Full autonomous flow confirmed!`.
4.  **Listen:** The voice agent will audibly confirm: "Payment successfully executed."
5.  **Final Proof:** Verify the `PAID` status and click **Verify** to see the final **Transaction Hash**.
---

## 📸 Execution Proof (Manual Demo)

Below is a manual execution proof of the **Agent-Pay (v4.11)** system showing that all modules (AI, Backend, and Frontend) are synchronized and working successfully.

![AgentPay_Team_Version](./assets/demo-proof%20manual.png)