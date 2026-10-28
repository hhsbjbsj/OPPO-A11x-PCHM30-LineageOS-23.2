import copy
import unittest
from resume import approved_for_exception


class ExceptionBoundaryTests(unittest.TestCase):
    def fixture(self):
        return {'all_candidate_hashes_match': True, 'apps': [1] * 5,
                'odm_jar_native_verification': [1] * 15,
                'vintf_without_runtime_info': {'dsds': 0, 'ssss': 0},
                'selinux_runtime': 0,
                'full_vintf_recheck': {
                    'dsds': {'code': 65, 'known_kernel_fcm_mismatch': True},
                    'ssss': {'code': 65, 'known_kernel_fcm_mismatch': True}}}

    def test_only_known_kernel_exception_is_eligible(self):
        self.assertTrue(approved_for_exception(self.fixture()))
        for mode in ('dsds', 'ssss'):
            r = self.fixture()
            r['full_vintf_recheck'][mode]['known_kernel_fcm_mismatch'] = False
            self.assertFalse(approved_for_exception(r))

    def test_any_hal_sdk_policy_or_hash_failure_blocks_packaging(self):
        for kind in ('dsds', 'ssss', 'policy', 'hash'):
            r = self.fixture()
            if kind in ('dsds', 'ssss'):
                r['vintf_without_runtime_info'][kind] = 65
            elif kind == 'policy':
                r['selinux_runtime'] = 255
            else:
                r['all_candidate_hashes_match'] = False
            self.assertFalse(approved_for_exception(r))

    def test_missing_consumer_verification_blocks_packaging(self):
        for key in ('apps', 'odm_jar_native_verification'):
            r = self.fixture()
            r[key].pop()
            self.assertFalse(approved_for_exception(r))


if __name__ == '__main__':
    unittest.main()
