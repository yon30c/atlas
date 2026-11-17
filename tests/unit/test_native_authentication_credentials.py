import unittest

from argon2 import extract_parameters

from atlas.adapters.argon2id_password_hasher import Argon2idPasswordHasher
from atlas.authentication.credentials import (
    LoginHandle,
    validate_new_password,
    validate_password_for_verification,
)
from atlas.authentication.password_hashing import Argon2idParameters
from atlas.core.errors import ContractError


class LoginHandleTests(unittest.TestCase):
    def test_normalizes_ascii_case(self):
        self.assertEqual(LoginHandle("Atlas.Admin").value, "atlas.admin")

    def test_rejects_non_ascii_and_invalid_shapes(self):
        for value in ("ab", " leading", "trailing ", "a/bc", "ñandú", "a" * 65, ""):
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    LoginHandle(value)

    def test_accepts_boundary_lengths(self):
        self.assertEqual(len(LoginHandle("abc").value), 3)
        self.assertEqual(len(LoginHandle("a" + "b" * 63).value), 64)


class PasswordPolicyTests(unittest.TestCase):
    def test_minimum_is_code_points_not_utf8_bytes(self):
        self.assertEqual(len(validate_new_password("á" * 12)), 24)
        with self.assertRaises(ContractError):
            validate_new_password("short")

    def test_maximum_is_utf8_bytes(self):
        validate_new_password("á" * 512)
        with self.assertRaises(ContractError):
            validate_new_password("á" * 513)

    def test_rejects_nul_and_unpaired_surrogates(self):
        for value in ("valid-password\x00suffix", "valid-password\ud800"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ContractError):
                    validate_new_password(value)

    def test_verification_does_not_apply_new_password_minimum(self):
        validate_password_for_verification("short-password")
        validate_password_for_verification("x")


class Argon2idPasswordHasherTests(unittest.TestCase):
    def setUp(self):
        self.parameters = Argon2idParameters(
            time_cost=1,
            memory_cost_kib=8192,
            parallelism=1,
            hash_len=32,
            salt_len=16,
        )
        self.hasher = Argon2idPasswordHasher(self.parameters)

    def test_hash_uses_argon2id_and_verifies(self):
        encoded = self.hasher.hash_password("correct horse battery")
        self.assertEqual(extract_parameters(encoded).type.name, "ID")
        self.assertTrue(self.hasher.verify_password(encoded, "correct horse battery"))
        self.assertFalse(self.hasher.verify_password(encoded, "incorrect horse battery"))

    def test_each_hash_uses_a_distinct_salt(self):
        first = self.hasher.hash_password("correct horse battery")
        second = self.hasher.hash_password("correct horse battery")
        self.assertNotEqual(first, second)

    def test_hash_is_not_rehashed_when_parameters_match(self):
        encoded = self.hasher.hash_password("correct horse battery")
        self.assertFalse(self.hasher.needs_rehash(encoded))

    def test_detects_parameters_that_need_rehash(self):
        old = Argon2idPasswordHasher(
            Argon2idParameters(
                time_cost=1, memory_cost_kib=8192, parallelism=1,
                hash_len=16, salt_len=16,
            )
        ).hash_password("correct horse battery")
        self.assertTrue(self.hasher.needs_rehash(old))

    def test_invalid_hash_fails_closed(self):
        self.assertFalse(self.hasher.verify_password("not-a-phc-hash", "some password"))
        with self.assertRaises(ContractError):
            self.hasher.needs_rehash("not-a-phc-hash")

    def test_new_password_validation_precedes_hashing(self):
        with self.assertRaises(ContractError):
            self.hasher.hash_password("too short")


class Argon2idParametersTests(unittest.TestCase):
    def test_rejects_invalid_or_implicit_parameters(self):
        with self.assertRaises(ContractError):
            Argon2idParameters(0, 8192, 1, 32, 16)
        with self.assertRaises(ContractError):
            Argon2idParameters(1, 8, 2, 32, 16)
        with self.assertRaises(ContractError):
            Argon2idParameters(1, 8192, 1, 8, 16)
        with self.assertRaises(ContractError):
            Argon2idParameters(1, 8192, 1, 32, 8)


if __name__ == "__main__":
    unittest.main()
