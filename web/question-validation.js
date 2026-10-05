/* Rules are shared with the API. The API always validates, including without JavaScript. */
function questionIssue(question, rules) {
  if (typeof question !== 'string') return 'question_invalid';
  if (Array.from(question.trim()).length > (rules?.max_length || 1500)) return 'question_too_long';
  const text = question.replace(/\p{Cf}/gu, '').trim();
  if (!text) return 'question_empty';
  if (/[\p{Cc}\p{Cs}]/u.test(text.replace(/[\t\r\n]/g, ''))) return 'question_invalid';
  const tokens = (text.toLowerCase().match(/[\p{L}\p{N}]+/gu) || []).filter(token => /\p{L}/u.test(token));
  if (!tokens.length) return 'question_needs_topic';
  // If the shared rules have not loaded, leave semantic checks to the API.
  if (!rules) return null;
  const filler = new Set(rules.non_topic_words), noise = new Set(rules.noise_tokens);
  const meaningful = tokens.filter(token => !filler.has(token));
  if (!meaningful.length || meaningful.every(token =>
    Array.from(token).length < 2 || noise.has(token) ||
    (Array.from(token).length >= 3 && new Set(token).size === 1))) return 'question_needs_topic';
  return null;
}
if (typeof module !== 'undefined') module.exports = {questionIssue};
