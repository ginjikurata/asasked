const f = document.getElementById("f");
const msg = document.getElementById("msg");
const say = (t) => {
  msg.textContent = t;
  setTimeout(() => (msg.textContent = ""), 2500);
};
chrome.storage.local.get(["profile"], ({ profile }) => {
  if (profile) for (const [k, v] of Object.entries(profile)) if (f.elements[k]) f.elements[k].value = v;
});
f.addEventListener("submit", (e) => {
  e.preventDefault();
  const profile = Object.fromEntries([...new FormData(f)].map(([k, v]) => [k, String(v).trim()]));
  profile.country = profile.country.toUpperCase();
  chrome.storage.local.set({ profile }, () => say("Saved in this browser."));
});
document.getElementById("clear").onclick = () =>
  chrome.storage.local.remove(["profile", "order", "checkout"], () => {
    f.reset();
    say("Deleted.");
  });
