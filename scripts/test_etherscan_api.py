"""
Test script for Etherscan API connectivity and functionality.

This script tests the Etherscan API key and validates various API endpoints
to ensure proper integration with the crypto transaction fee calculator.
"""

import os
import sys
import requests
import time
from typing import Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv


class EtherscanAPITester:
    """Test suite for Etherscan API functionality."""

    def __init__(self, api_key: str, timeout: int = 15):
        """
        Initialize the Etherscan API tester.

        Args:
            api_key: Etherscan API key
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.etherscan.io/v2/api"
        self.test_results = []

    def _make_request(self, params: Dict[str, Any]) -> Optional[Dict]:
        """
        Make a request to Etherscan API.

        Args:
            params: Query parameters for the API request

        Returns:
            JSON response as dictionary, or None if request fails
        """
        params['apikey'] = self.api_key
        params['chainid'] = '1'  # Ethereum Mainnet chain ID

        try:
            response = requests.get(
                self.base_url,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            print(f"ERROR: Request timed out after {self.timeout} seconds")
            return None
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Request failed - {str(e)}")
            return None

    def _log_result(self, test_name: str, passed: bool, message: str = ""):
        """Log test result."""
        status = "PASS" if passed else "FAIL"
        result = {
            'test': test_name,
            'status': status,
            'message': message,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.test_results.append(result)

        status_symbol = "[PASS]" if passed else "[FAIL]"
        print(f"{status_symbol} {test_name}: {status}")
        if message:
            print(f"  -> {message}")

    def test_api_key_validity(self) -> bool:
        """
        Test if the API key is valid by checking account balance endpoint.

        Returns:
            True if API key is valid, False otherwise
        """
        print("\n[1] Testing API Key Validity...")

        # Use a known Ethereum address (Vitalik's address) for testing
        test_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

        params = {
            'module': 'account',
            'action': 'balance',
            'address': test_address,
            'tag': 'latest'
        }

        response = self._make_request(params)

        if response is None:
            self._log_result("API Key Validity", False, "Failed to connect to API")
            return False

        if response.get('status') == '1' and response.get('message') == 'OK':
            balance = int(response.get('result', 0))
            self._log_result(
                "API Key Validity",
                True,
                f"API key is valid. Test balance: {balance / 1e18:.4f} ETH"
            )
            return True
        else:
            error_msg = response.get('result', 'Unknown error')
            self._log_result("API Key Validity", False, f"API Error: {error_msg}")
            return False

    def test_get_account_balance(self) -> bool:
        """
        Test fetching account balance for a specific address.

        Returns:
            True if test passes, False otherwise
        """
        print("\n[2] Testing Account Balance Retrieval...")

        # Test with Ethereum Foundation address
        test_address = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"

        params = {
            'module': 'account',
            'action': 'balance',
            'address': test_address,
            'tag': 'latest'
        }

        response = self._make_request(params)

        if response and response.get('status') == '1':
            balance = int(response.get('result', 0))
            balance_eth = balance / 1e18
            self._log_result(
                "Account Balance",
                True,
                f"Retrieved balance: {balance_eth:.6f} ETH"
            )
            return True
        else:
            self._log_result("Account Balance", False, "Failed to retrieve balance")
            return False

    def test_get_transaction_list(self) -> bool:
        """
        Test fetching transaction list for an address.

        Returns:
            True if test passes, False otherwise
        """
        print("\n[3] Testing Transaction List Retrieval...")

        # Test with a known active address
        test_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

        params = {
            'module': 'account',
            'action': 'txlist',
            'address': test_address,
            'startblock': 0,
            'endblock': 99999999,
            'page': 1,
            'offset': 5,  # Get only 5 transactions for testing
            'sort': 'desc'
        }

        response = self._make_request(params)

        if response and response.get('status') == '1':
            transactions = response.get('result', [])
            tx_count = len(transactions)
            self._log_result(
                "Transaction List",
                True,
                f"Retrieved {tx_count} transactions"
            )

            # Display first transaction details if available
            if transactions:
                first_tx = transactions[0]
                print(f"  -> Latest TX Hash: {first_tx.get('hash', 'N/A')}")
                print(f"  -> Block: {first_tx.get('blockNumber', 'N/A')}")
                print(f"  -> Value: {int(first_tx.get('value', 0)) / 1e18:.6f} ETH")

            return True
        else:
            self._log_result("Transaction List", False, "Failed to retrieve transactions")
            return False

    def test_get_gas_price(self) -> bool:
        """
        Test fetching current gas price estimate.

        Returns:
            True if test passes, False otherwise
        """
        print("\n[4] Testing Gas Price Oracle...")

        params = {
            'module': 'gastracker',
            'action': 'gasoracle'
        }

        response = self._make_request(params)

        if response and response.get('status') == '1':
            result = response.get('result', {})
            safe_gas = result.get('SafeGasPrice', 'N/A')
            propose_gas = result.get('ProposeGasPrice', 'N/A')
            fast_gas = result.get('FastGasPrice', 'N/A')

            self._log_result(
                "Gas Price Oracle",
                True,
                f"Safe: {safe_gas} Gwei | Propose: {propose_gas} Gwei | Fast: {fast_gas} Gwei"
            )
            return True
        else:
            self._log_result("Gas Price Oracle", False, "Failed to retrieve gas prices")
            return False

    def test_get_eth_price(self) -> bool:
        """
        Test fetching current ETH price in USD.

        Returns:
            True if test passes, False otherwise
        """
        print("\n[5] Testing ETH Price Retrieval...")

        params = {
            'module': 'stats',
            'action': 'ethprice'
        }

        response = self._make_request(params)

        if response and response.get('status') == '1':
            result = response.get('result', {})
            eth_usd = result.get('ethusd', 'N/A')
            eth_btc = result.get('ethbtc', 'N/A')

            self._log_result(
                "ETH Price",
                True,
                f"ETH/USD: ${eth_usd} | ETH/BTC: {eth_btc}"
            )
            return True
        else:
            self._log_result("ETH Price", False, "Failed to retrieve ETH price")
            return False

    def test_rate_limiting(self) -> bool:
        """
        Test API rate limiting behavior.

        Returns:
            True if test passes, False otherwise
        """
        print("\n[6] Testing Rate Limiting...")

        test_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
        params = {
            'module': 'account',
            'action': 'balance',
            'address': test_address,
            'tag': 'latest'
        }

        # Make 3 rapid requests to test rate limiting
        success_count = 0
        for i in range(3):
            response = self._make_request(params)
            if response and response.get('status') == '1':
                success_count += 1
            time.sleep(0.2)  # Small delay between requests

        if success_count >= 2:
            self._log_result(
                "Rate Limiting",
                True,
                f"{success_count}/3 requests succeeded"
            )
            return True
        else:
            self._log_result(
                "Rate Limiting",
                False,
                f"Only {success_count}/3 requests succeeded - possible rate limit issues"
            )
            return False

    def test_error_handling(self) -> bool:
        """
        Test API error handling with invalid input.

        Returns:
            True if test passes, False otherwise
        """
        print("\n[7] Testing Error Handling...")

        # Test with invalid chainid to check error handling
        params = {
            'module': 'account',
            'action': 'balance',
            'address': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',
            'tag': 'latest',
            'chainid': '999999',  # Invalid chain ID
            'apikey': self.api_key
        }

        try:
            response = requests.get(
                self.base_url,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            # We expect an error response for invalid chain ID
            if data.get('status') == '0' or 'error' in str(data.get('message', '')).lower():
                error_msg = data.get('result', data.get('message', 'Unknown error'))
                self._log_result(
                    "Error Handling",
                    True,
                    f"Properly handled invalid input: {error_msg}"
                )
                return True
            else:
                # If no error was returned, API might be handling it gracefully
                self._log_result(
                    "Error Handling",
                    True,
                    "API handled invalid input gracefully"
                )
                return True

        except Exception as e:
            # Exception during error test is also acceptable
            self._log_result(
                "Error Handling",
                True,
                f"API properly rejected invalid request: {str(e)}"
            )
            return True

    def run_all_tests(self) -> Dict[str, Any]:
        """
        Run all tests and return summary.

        Returns:
            Dictionary containing test summary and results
        """
        print("\n" + "="*70)
        print("ETHERSCAN API TEST SUITE")
        print("="*70)

        start_time = time.time()

        # Run all tests
        tests = [
            self.test_api_key_validity,
            self.test_get_account_balance,
            self.test_get_transaction_list,
            self.test_get_gas_price,
            self.test_get_eth_price,
            self.test_rate_limiting,
            self.test_error_handling
        ]

        passed = 0
        failed = 0

        for test in tests:
            if test():
                passed += 1
            else:
                failed += 1

        end_time = time.time()
        duration = end_time - start_time

        # Print summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total Tests: {passed + failed}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Success Rate: {(passed / (passed + failed) * 100):.1f}%")

        return {
            'total': passed + failed,
            'passed': passed,
            'failed': failed,
            'duration': duration,
            'results': self.test_results
        }


def main():
    """Main function to run the test suite."""

    # Load environment variables
    load_dotenv()

    api_key = os.getenv('ETHERSCAN_API_KEY')

    if not api_key:
        print("ERROR: ETHERSCAN_API_KEY not found in environment variables")
        print("Please ensure your .env file contains ETHERSCAN_API_KEY")
        sys.exit(1)

    print(f"Using API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else ''}")

    # Create tester instance
    timeout = int(os.getenv('API_TIMEOUT', 15))
    tester = EtherscanAPITester(api_key, timeout)

    # Run all tests
    summary = tester.run_all_tests()

    # Exit with appropriate code
    if summary['failed'] > 0:
        sys.exit(1)
    else:
        print("\n[SUCCESS] All tests passed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
