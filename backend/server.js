// --- Agent-Pay Backend Service (Module 2) - v4.10 Executor ---
// Date: 2025-11-07
// Goal: Final Executor version, now includes INSUFFICIENT_BALANCE detection.

// 1. Module Imports
const express = require('express');
const ethers = require('ethers');
const cors = require('cors');
require('dotenv').config(); 
const axios = require('axios'); 

// 2. Load Environment Variables and ABI
const ROUTER_ADDRESS = process.env.PAYMENT_ROUTER_ADDRESS;
const PRIVATE_KEY = process.env.BACKEND_WALLET_PRIVATE_KEY;
const RPC_URL = process.env.ARC_RPC_ENDPOINT;
const ELEVENLABS_KEY = process.env.ELEVENLABS_API_KEY; 

// Load the ABI from the v2.0 contract
const routerABI = require('./PaymentRouter.json').abi;

// --- ElevenLabs Agent Configuration ---
const AGENT_VOICE_ID = "agent_0601k92gn3p1ftdszwze7k2zx2xx"; 
const ELEVENLABS_AGENT_URL = `https://api.elevenlabs.io/v1/agent/${AGENT_VOICE_ID}/talk-to`;

// 3. Web3 Initialization
const provider = new ethers.JsonRpcProvider(RPC_URL);
const signer = new ethers.Wallet(PRIVATE_KEY, provider);
const paymentContract = new ethers.Contract(ROUTER_ADDRESS, routerABI, signer);

console.log(`✅ Connected to Arc Testnet.`);
console.log(`✅ Router Contract (v2.0): ${ROUTER_ADDRESS}`);
console.log(`✅ Backend Signer: ${signer.address}`);

// 5. Server Setup
const app = express();
const PORT = 5001;

const corsOptions = {
    origin: ['http://localhost:8000', 'http://localhost:5000']
};
app.use(cors(corsOptions));
app.use(express.json());

// --- Voice Notification Function (Remains the same) ---
async function triggerVoiceNotification(text, invoiceId) {
    console.log(`[VOICE] Sending: "${text}"`);
    try {
        const response = await axios.post(
            ELEVENLABS_AGENT_URL,
            { "text": text, "context_id": invoiceId },
            { 
                headers: { "Content-Type": "application/json", "xi-api-key": ELEVENLABS_KEY },
                responseType: 'arraybuffer' 
            }
        );
        if (response.status === 200) {
            console.log(`[VOICE] Notification for ${invoiceId} sent successfully.`);
        }
    } catch (error) {
        console.error(`[VOICE] CRITICAL: Failed to send voice notification: ${error.message}`);
    }
}

// --- API Endpoints ---

// --- 🚀 v4.10 NEW: Endpoint for AI Agent to check balance ---
app.get('/api/check-balance', async (req, res) => {
    try {
        const usdcAddress = "0x3600000000000000000000000000000000000000";
        const usdcABI = ["function balanceOf(address account) view returns (uint256)"];
        const usdcContract = new ethers.Contract(usdcAddress, usdcABI, provider);

        const rawBalance = await usdcContract.balanceOf(signer.address);
        const balance = ethers.formatUnits(rawBalance, 6); 

        // Returns { balance: "18.92" }
        res.status(200).send({ balance: balance });
    } catch (error) {
        console.error(`[CRITICAL] Error in /api/check-balance: ${error.message}`);
        res.status(500).send({ error: "Failed to fetch wallet balance from blockchain." });
    }
});
// --- 🚀 v4.10 END NEW ENDPOINT ---

// --- 🚀 UPDATED: /api/create-on-chain (with Error Handling) ---
app.post('/api/create-on-chain', async (req, res) => {
    const { invoiceId, amount, recipientAddress, condition } = req.body;
    console.log(`[EXECUTOR] Received task to create on-chain payment for: ${invoiceId}`);

    try {
        const amountInCents = ethers.parseUnits(amount.toString(), 6); 
        
        console.log(`[EXECUTOR] Funding Vault (${ROUTER_ADDRESS}) with ${amount} USDC...`);
        const usdcABI = ["function transfer(address to, uint amount) returns (bool)"];
        const usdcAddress = "0x3600000000000000000000000000000000000000"; 
        const usdcContract = new ethers.Contract(usdcAddress, usdcABI, signer);

        const fundTx = await usdcContract.transfer(ROUTER_ADDRESS, amountInCents);
        await fundTx.wait();
        console.log(`[EXECUTOR] Vault successfully funded.`);

        const tx = await paymentContract.createPayment(invoiceId, amountInCents, recipientAddress);
        await tx.wait(); 
        console.log(`[EXECUTOR] Payment entry created on-chain. Confirmed.`);
        
        res.status(201).send({ message: "Payment created on-chain" });

    } catch (error) {
        console.error(`[CRITICAL] Error in /api/create-on-chain: ${error.message}`);
        
        // --- 🚀 v4.10 IMPROVEMENT: Recognize INSUFFICIENT_BALANCE error ---
        const errorDetail = error.message.includes("transfer amount exceeds balance") 
                            ? "INSUFFICIENT_BALANCE" 
                            : error.message;
        
        res.status(500).send({ error: errorDetail });
    }
});

// --- 🚀 UPDATED: /api/trigger-payment (Remains the same) ---
app.post('/api/trigger-payment', async (req, res) => {
    const { invoiceId } = req.body;
    console.log(`[EXECUTOR] Received EXECUTE trigger from AI Brain for: ${invoiceId}`);

    try {
        console.log(`[EXECUTOR] Calling 'setPaymentFulfilled' for ${invoiceId}...`);
        const fulfillTx = await paymentContract.setPaymentFulfilled(invoiceId);
        await fulfillTx.wait();
        console.log(`[EXECUTOR] Fulfillment confirmed on-chain (Vault Unlocked).`);

        console.log(`[EXECUTOR] Calling 'executePayment' for ${invoiceId}...`);
        const executeTx = await paymentContract.executePayment(invoiceId);
        await executeTx.wait();
        console.log(`[EXECUTOR] Payment executed. USDC Sent!`);

        await triggerVoiceNotification(`Payment for invoice ${invoiceId} has been successfully executed.`, invoiceId);

        const txHash = executeTx.hash; 
        const timestamp = new Date().toISOString(); 
        
        res.status(200).send({ 
            message: "Payment executed successfully!",
            transactionHash: txHash,
            paidAt: timestamp
        });

    } catch (error) {
        console.error(`[CRITICAL] Error in /api/trigger-payment: ${error.message}`);
        await triggerVoiceNotification(`Alert. Payment trigger for invoice ${invoiceId} has failed. Please check the system.`, invoiceId);
        res.status(500).send({ error: "Failed to execute payment after fulfillment." });
    }
});

// --- Endpoint for the Dashboard to get the current USDC balance (Stays the same) ---
app.get('/api/wallet-balance', async (req, res) => {
    try {
        const usdcAddress = "0x3600000000000000000000000000000000000000";
        const usdcABI = ["function balanceOf(address account) view returns (uint256)"];
        const usdcContract = new ethers.Contract(usdcAddress, usdcABI, provider);
        const rawBalance = await usdcContract.balanceOf(signer.address);
        const balance = ethers.formatUnits(rawBalance, 6); 

        res.status(200).send({ balance: balance, address: signer.address });
    } catch (error) {
        console.error(`[CRITICAL] Error fetching balance: ${error.message}`);
        res.status(500).send({ error: "Failed to fetch wallet balance." });
    }
});

// Start Server
app.listen(PORT, () => {
    console.log(`🚀 Agent-Pay Backend v4.10 (Executor) running on http://localhost:${PORT}`);
    console.log(`--- Awaiting commands from AI Brain (port 5000) ---`);
});