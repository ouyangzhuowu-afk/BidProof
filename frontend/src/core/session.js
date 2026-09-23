// @ts-check
/** An epoch separates work started under different authenticated sessions. */
let epoch = 0;
export const sessionVersion = () => epoch;
export function invalidateSession() { epoch += 1; }
/** @param {number} version */
export const isSessionCurrent = (version) => version === epoch;
