// The API base comes from the build environment so the same bundle can point
// at a local sam invoke or the deployed HttpApi without a code change.
const BASE = import.meta.env.VITE_API_URL || "";

export async function ask(conversation, asked, answers) {
  const response = await fetch(`${BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation, asked, answers }),
  });
  if (!response.ok) throw new Error(`api returned ${response.status}`);
  return response.json();
}
