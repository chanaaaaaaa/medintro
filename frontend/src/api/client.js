const API = "";

async function parseError(res) {
  let msg = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body.detail) {
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    /* ignore */
  }
  return msg;
}

export async function apiRegister(payload) {
  const res = await fetch(`${API}/api/queue/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function apiHall(queueId) {
  const res = await fetch(`${API}/api/queue/hall/${queueId}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function apiAdvanceNext() {
  const res = await fetch(`${API}/api/queue/advance-next`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
