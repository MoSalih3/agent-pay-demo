// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {PaymentRouter} from "../src/PaymentRouter.sol";

interface IERC20 {
    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function approve(address spender, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
    function decimals() external view returns (uint8);
}

// Minimal 6-decimals ERC20 for tests
contract MockUSDC is IERC20 {
    string public name = "Mock USDC";
    string public symbol = "mUSDC";
    uint8 public override decimals = 6;
    uint256 public override totalSupply;
    mapping(address => uint256) public override balanceOf;
    mapping(address => mapping(address => uint256)) public override allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
    }

    function transfer(address to, uint256 value) external override returns (bool) {
        balanceOf[msg.sender] -= value;
        balanceOf[to] += value;
        return true;
    }

    function approve(address spender, uint256 value) external override returns (bool) {
        allowance[msg.sender][spender] = value;
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external override returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= value, "allowance");
        allowance[from][msg.sender] = allowed - value;
        balanceOf[from] -= value;
        balanceOf[to] += value;
        return true;
    }
}

contract PaymentRouterTest is Test {
    MockUSDC usdc;
    PaymentRouter router;
    address owner = address(0xBEEF);
    address manager = address(0xB0B);
    address recipient = address(0xCAFE);

    function setUp() public {
        usdc = new MockUSDC();
        router = new PaymentRouter(address(usdc), owner, manager);

        // fund manager
        usdc.mint(manager, 10_000_000); // 10 USDC
        vm.prank(manager);
        usdc.approve(address(router), type(uint256).max);
    }

    function test_DepositAndExecute() public {
        // manager deposits 5 USDC
        vm.prank(manager);
        router.depositFromManager(5_000_000);

        // owner sets payment
        bytes32 invoiceId = keccak256("INV-1");
        vm.prank(owner);
        router.upsertPayment(invoiceId, recipient, 3_000_000);

        // cannot execute before fulfilled
        vm.prank(owner);
        vm.expectRevert();
        router.executePayment(invoiceId);

        // fulfill then execute
        vm.prank(owner);
        router.setPaymentFulfilled(invoiceId, true);

        vm.prank(owner);
        router.executePayment(invoiceId);

        assertEq(usdc.balanceOf(recipient), 3_000_000);
    }
}
