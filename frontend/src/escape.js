/**
 * HTML escaping. Tagged templates interpolate as text unless the value is already SafeHtml,
 * so a render path cannot forget to escape a user-supplied string.
 *
 * @typedef {object} SafeHtml
 * @property {string} value
 */

/** @param {unknown} value */
export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[character]
  ));
}

/**
 * @param {unknown} value
 * @returns {SafeHtml}
 */
export function raw(value) {
  return { __safe: true, value: String(value ?? ''), toString() { return this.value; } };
}

/**
 * @param {unknown} value
 * @returns {string}
 */
export function toHtml(value) {
  if (value == null || value === false) return '';
  if (Array.isArray(value)) return value.map(toHtml).join('');
  if (typeof value === 'object' && value.__safe) return value.value;
  return escapeHtml(value);
}

/**
 * @param {TemplateStringsArray} strings
 * @param {...unknown} values
 * @returns {SafeHtml}
 */
export function html(strings, ...values) {
  let output = strings[0];
  for (let index = 0; index < values.length; index += 1) {
    output += toHtml(values[index]) + strings[index + 1];
  }
  return raw(output);
}

/**
 * @param {Element} element
 * @param {unknown} content
 */
export function setHtml(element, content) {
  element.innerHTML = toHtml(content);
}
