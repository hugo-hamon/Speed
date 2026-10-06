export async function call(name, ...args) {
  if (!window.eel || typeof window.eel[name] !== 'function') {
    throw new Error('La liaison avec Python est indisponible. Lance le jeu avec « python app.py », puis ouvre son adresse locale.');
  }
  let timer;
  try {
    const response = await Promise.race([
      window.eel[name](...args)(),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Le moteur ne répond plus. Vérifie que Python fonctionne, puis recharge la page.')), 12000); }),
    ]);
    if (!response?.ok) throw new Error(response?.error || 'Le moteur a renvoyé une réponse inattendue.');
    return response.data;
  } finally { clearTimeout(timer); }
}
