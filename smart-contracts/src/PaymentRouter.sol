// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/*
 * Arc Testnet USDC (ERC-20 interface):
 *   0x3600000000000000000000000000000000000000
 * Decimals: 6
 */

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract PaymentRouter is Ownable2Step, ReentrancyGuard {
    using SafeERC20 for IERC20;

    /// @notice USDC (ERC-20) on Arc Testnet
    IERC20 public immutable USDC;

    /// @notice Optional designated funder whose wallet provides liquidity
    address public manager;

    struct ConditionalPayment {
        uint256 amount;     // USDC amount (6 decimals)
        address recipient;  // payout address
        bool isFulfilled;   // set by owner when off-chain condition met
        bool exists;        // guard
    }

    mapping(bytes32 => ConditionalPayment) public payments;

    event ManagerUpdated(address indexed oldManager, address indexed newManager);
    event Funded(address indexed from, uint256 amount);
    event PaymentUpserted(bytes32 indexed invoiceId, address indexed recipient, uint256 amount);
    event PaymentFulfilled(bytes32 indexed invoiceId, bool isFulfilled);
    event PaymentExecuted(bytes32 indexed invoiceId, address indexed to, uint256 amount);

    constructor(address usdc_, address initialOwner, address manager_) {
        require(usdc_ != address(0) && initialOwner != address(0), "Zero address");
        USDC = IERC20(usdc_);
        _transferOwnership(initialOwner);
        manager = manager_;
    }

    // ========= Admin (backend owner) =========

    function upsertPayment(bytes32 invoiceId, address recipient, uint256 amount) external onlyOwner {
        require(recipient != address(0), "Bad recipient");
        require(amount > 0, "Zero amount");
        ConditionalPayment storage p = payments[invoiceId];
        p.amount = amount;
        p.recipient = recipient;
        p.exists = true;
        emit PaymentUpserted(invoiceId, recipient, amount);
    }

    function setPaymentFulfilled(bytes32 invoiceId, bool fulfilled) external onlyOwner {
        ConditionalPayment storage p = payments[invoiceId];
        require(p.exists, "Invoice missing");
        p.isFulfilled = fulfilled;
        emit PaymentFulfilled(invoiceId, fulfilled);
    }

    function executePayment(bytes32 invoiceId) external onlyOwner nonReentrant {
        ConditionalPayment storage p = payments[invoiceId];
        require(p.exists, "Invoice missing");
        require(p.isFulfilled, "Not fulfilled");
        require(p.amount > 0, "No amount");

        uint256 bal = USDC.balanceOf(address(this));
        require(bal >= p.amount, "Insufficient funds");

        address to = p.recipient;
        uint256 amt = p.amount;

        // Effects first
        p.amount = 0;
        p.isFulfilled = false;

        USDC.safeTransfer(to, amt);
        emit PaymentExecuted(invoiceId, to, amt);
    }

    function setManager(address newManager) external onlyOwner {
        emit ManagerUpdated(manager, newManager);
        manager = newManager;
    }

    function rescueTokens(address token, address to, uint256 amount) external onlyOwner {
        require(to != address(0), "Zero to");
        IERC20(token).transfer(to, amount);
    }

    // ========= Funding =========

    /// @notice Manager can deposit via allowance-pull
    function depositFromManager(uint256 amount) external {
        require(msg.sender == manager, "Only manager");
        require(amount > 0, "Zero amount");
        USDC.safeTransferFrom(msg.sender, address(this), amount);
        emit Funded(msg.sender, amount);
    }

    /// @notice Any account may push USDC into the contract via transferFrom
    function deposit(uint256 amount) external {
        require(amount > 0, "Zero amount");
        USDC.safeTransferFrom(msg.sender, address(this), amount);
        emit Funded(msg.sender, amount);
    }

    // ========= Views =========

    function getPayment(bytes32 invoiceId)
        external
        view
        returns (uint256 amount, address recipient, bool isFulfilled, bool exists)
    {
        ConditionalPayment memory p = payments[invoiceId];
        return (p.amount, p.recipient, p.isFulfilled, p.exists);
    }
}
