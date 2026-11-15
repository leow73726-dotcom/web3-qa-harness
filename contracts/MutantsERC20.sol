// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./SimpleERC20.sol";

/// @notice 变异体 A：`transferFrom` 忘记递减 allowance。
///         现实里最常见的 ERC-20 缺陷之一 —— 无限授权拿不完，额度形同虚设。
///         期望被 `test_transfer_from_consumes_allowance` 杀灭。
contract NoAllowanceDecrementERC20 is SimpleERC20 {
    constructor(string memory _name, string memory _symbol, uint8 _decimals, uint256 _supply)
        SimpleERC20(_name, _symbol, _decimals, _supply)
    {}

    function transferFrom(address from, address to, uint256 value)
        external
        override
        returns (bool)
    {
        // 缺陷：只做转账，不扣 allowance
        _transfer(from, to, value);
        return true;
    }
}

/// @notice 变异体 B：`_transfer` 跳过余额检查（unchecked 下溢回绕）。
///         效果是「余额不足也能转」，且余额会变成天文数字。
///         期望被 `test_transfer_more_than_balance_reverts_with_custom_error`
///         与守恒不变量同时杀灭。
contract NoBalanceCheckERC20 is SimpleERC20 {
    constructor(string memory _name, string memory _symbol, uint8 _decimals, uint256 _supply)
        SimpleERC20(_name, _symbol, _decimals, _supply)
    {}

    function _transfer(address from, address to, uint256 value) internal override {
        // 缺陷：没有 require(balance >= value)
        unchecked {
            balanceOf[from] -= value;
            balanceOf[to] += value;
        }
        emit Transfer(from, to, value);
    }
}
