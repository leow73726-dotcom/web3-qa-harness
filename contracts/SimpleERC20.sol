// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title SimpleERC20
/// @notice 一个自包含的 ERC-20 实现，专门给回归测试当「被测业务合约」。
///         不依赖 OpenZeppelin，避免外部 import 让编译产物不可复现。
///
/// 有意保留的三处真实业务边界（也是测试重点）：
///   1. 余额不足 / 授权不足都抛**自定义错误**（selector + 参数），而不是空 revert
///   2. `transferFrom` 在无限授权（type(uint256).max）下**不递减** allowance
///   3. 自转账、零金额转账都合法，且都要发事件
contract SimpleERC20 {
    string public name;
    string public symbol;
    uint8 public immutable decimals;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    error InsufficientBalance(address owner, uint256 available, uint256 required);
    error InsufficientAllowance(address owner, uint256 available, uint256 required);

    constructor(string memory _name, string memory _symbol, uint8 _decimals, uint256 _supply) {
        name = _name;
        symbol = _symbol;
        decimals = _decimals;
        totalSupply = _supply;
        balanceOf[msg.sender] = _supply;
        emit Transfer(address(0), msg.sender, _supply);
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external virtual returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        if (allowed < value) {
            revert InsufficientAllowance(from, allowed, value);
        }
        if (allowed != type(uint256).max) {
            allowance[from][msg.sender] = allowed - value;
        }
        _transfer(from, to, value);
        return true;
    }

    function _transfer(address from, address to, uint256 value) internal virtual {
        uint256 available = balanceOf[from];
        if (available < value) {
            revert InsufficientBalance(from, available, value);
        }
        unchecked {
            balanceOf[from] = available - value;
            balanceOf[to] += value;
        }
        emit Transfer(from, to, value);
    }
}
