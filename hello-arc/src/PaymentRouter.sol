// --- Agent-Pay Smart Contract (Module 1) - v2.0 with Events ---
// Date: 2025-11-06
// Author: Eng.Saif_SAST
// Goal: The on-chain "Vault" to hold funds and execute conditional payments.
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title PaymentRouter
 * @dev This contract acts as a conditional vault (escrow) for autonomous payments.
 * It is owned by the Backend Server (Module 2).
 * It holds USDC funds sent from the Backend and releases them to a recipient
 * only after the AI Agent (Module 3) verifies a condition.
 */
contract PaymentRouter is Ownable {

    IERC20 public usdcToken; 

    /**
     * @dev Defines the structure for a payment.
     */
    struct PaymentCondition {
        uint256 amount;
        address recipientAddress;
        bool isFulfilled;
        bool isPaid;
    }

    // Maps the Invoice ID (string) to its payment conditions.
    mapping(string => PaymentCondition) public paymentConditions; 

    // --- 🚀 NEW ADDITION: Events ---
    // Emitted when a new payment is registered (in createPayment)
    event PaymentCreated(string indexed invoiceId, uint256 amount, address indexed recipient);
    // Emitted when the AI confirms the condition (in setPaymentFulfilled)
    event PaymentFulfilled(string indexed invoiceId);
    // Emitted when the final USDC transfer is executed (in executePayment)
    event PaymentExecuted(string indexed invoiceId, address indexed recipient, uint256 amount);
    // --- 🚀 END ADDITION ---

    /**
     * @dev Sets the owner (our Backend Server) and the USDC token address.
     * @param _usdcAddress The official address of USDC on Arc Testnet.
     */
    constructor(address _usdcAddress) Ownable(msg.sender) {
        usdcToken = IERC20(_usdcAddress);
    }

    /**
     * @dev Called by the Backend to register a new payment.
     * The Backend MUST fund this contract with the exact 'amount' *before* calling this.
     */
    function createPayment(string memory _invoiceId, uint256 _amount, address _recipient) public onlyOwner {
        require(paymentConditions[_invoiceId].amount == 0, "Invoice already exists");
        paymentConditions[_invoiceId] = PaymentCondition(_amount, _recipient, false, false);
        
        // --- 🚀 EMIT EVENT ---
        emit PaymentCreated(_invoiceId, _amount, _recipient);
    }

    /**
     * @dev Called by the Backend *after* the AI Agent confirms the condition.
     * This function "unlocks" the payment.
     */
    function setPaymentFulfilled(string memory _invoiceId) public onlyOwner {
        require(paymentConditions[_invoiceId].amount > 0, "Invoice not found");
        paymentConditions[_invoiceId].isFulfilled = true;

        // --- 🚀 EMIT EVENT ---
        emit PaymentFulfilled(_invoiceId);
    }

    /**
     * @dev Called by the Backend to execute the final payment.
     * This function sends the funds from this contract to the final recipient.
     */
    function executePayment(string memory _invoiceId) public onlyOwner {
        PaymentCondition storage payment = paymentConditions[_invoiceId];
        // Check all conditions
        require(payment.amount > 0, "Invoice not found");
        require(payment.isFulfilled == true, "Condition not met"); // Check the "unlock"
        require(payment.isPaid == false, "Payment already made");
        
        payment.isPaid = true;
        
        // Execute the final transfer from this contract to the recipient
        usdcToken.transfer(payment.recipientAddress, payment.amount);

        // --- 🚀 EMIT EVENT ---
        emit PaymentExecuted(_invoiceId, payment.recipientAddress, payment.amount);
    }
}