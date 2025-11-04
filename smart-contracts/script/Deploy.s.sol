// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import {PaymentRouter} from "../src/PaymentRouter.sol";

contract Deploy is Script {
    function run() external {
        // Read env
        address USDC = vm.envAddress("ARC_USDC");
        address OWNER = vm.envAddress("BACKEND_OWNER");
        address MANAGER = vm.envOr("MANAGER", address(0));

        vm.startBroadcast(vm.envUint("PRIVATE_KEY"));
        PaymentRouter router = new PaymentRouter(USDC, OWNER, MANAGER);
        vm.stopBroadcast();

        console2.log("PaymentRouter deployed at:", address(router));
        console2.log("USDC:", USDC);
        console2.log("OWNER:", OWNER);
        console2.log("MANAGER:", MANAGER);
    }
}
