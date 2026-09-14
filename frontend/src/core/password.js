/** Account password policy — keep in sync with `app/schemas.py`. */

export const MIN_PASSWORD_LENGTH = 8;
export const PASSWORD_POLICY_HINT = '至少 8 位，须同时包含字母和数字。';
export const PASSWORD_POLICY_MESSAGE = '密码至少 8 位，且须同时包含字母和数字';

/** @param {string} password */
export function passwordMeetsPolicy(password) {
  if (typeof password !== 'string' || password.length < MIN_PASSWORD_LENGTH) return false;
  return /[A-Za-z]/.test(password) && /\d/.test(password);
}

/** @param {string} password @returns {asserts password is string} */
export function assertPasswordPolicy(password) {
  if (!passwordMeetsPolicy(password)) {
    throw new Error(PASSWORD_POLICY_MESSAGE);
  }
}
