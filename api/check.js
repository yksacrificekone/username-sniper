module.exports = async (req, res) => {
  // Simple checker API for GitHub usernames. Expects JSON POST { username: "name" }
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ ok: false, msg: 'method not allowed' });
  }

  const { username } = req.body || {};
  if (!username || typeof username !== 'string') return res.status(400).json({ ok: false, msg: 'missing username' });

  // Basic validation: only allow common username chars to avoid abuse
  const valid = /^[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9]))*[a-z0-9]$/i;
  if (!valid.test(username)) return res.json({ ok: true, status: 'invalid' });

  try {
    // Use global fetch (available on Vercel Node runtime). Timeout via AbortController.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const url = `https://github.com/${encodeURIComponent(username)}`;
    const resp = await fetch(url, { method: 'GET', redirect: 'manual', signal: controller.signal });
    clearTimeout(timeout);

    const status = resp.status;
    if (status === 404 || status === 410) return res.json({ ok: true, status: 'available', httpStatus: status });
    if (status === 200 || status === 301 || status === 302) return res.json({ ok: true, status: 'taken', httpStatus: status });
    if (status === 429 || status === 403) return res.json({ ok: true, status: 'ratelimit', httpStatus: status });
    return res.json({ ok: true, status: 'error', httpStatus: status });
  } catch (err) {
    const msg = err && err.name === 'AbortError' ? 'timeout' : String(err && err.message || err);
    return res.json({ ok: false, status: 'error', msg });
  }
};
