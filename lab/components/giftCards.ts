// Gift cards sold for crypto by CoinGate (coingate.com/gift-cards, field s) and Coinsbee
// (coinsbee.com/en/gift-cards/<category>/<slug>/, field cb). Slugs were taken from links on those sites'
// own pages on 2026-11-18. A query word matching any keyword shows the card next to store results.
// AFFILIATE / CB_AFFILIATE: once the owner has an affiliate link, put its query string here (e.g. "?ref=XXXX").
export const AFFILIATE = "";
export const GIFT_BASE = "https://coingate.com/gift-cards/";
export const CB_AFFILIATE = "";
export const CB_BASE = "https://www.coinsbee.com/en/gift-cards/";

export type GiftCard = { n: string; s?: string; cb?: string; k: string[] };

export const GIFT_CARDS: GiftCard[] = [
  { n: "Amazon", s: "amazon", cb: "e-commerce/amazon", k: ["amazon", "books", "kindle", "electronics", "headphones", "laptop", "phone", "camera", "toys"] },
  { n: "Walmart", s: "walmart", cb: "e-commerce/walmart", k: ["walmart", "groceries", "grocery", "tv", "toys", "furniture"] },
  { n: "Target", s: "target", cb: "e-commerce/target", k: ["target", "toys", "home", "furniture"] },
  { n: "eBay", s: "ebay", cb: "e-commerce/ebay", k: ["ebay", "used", "vintage", "collectibles", "cards", "watch", "watches"] },
  { n: "Apple", s: "apple", cb: "entertainment/apple", k: ["apple", "iphone", "ipad", "macbook", "mac", "airpods"] },
  { n: "Home Depot", s: "home-depot", cb: "home-and-garden/the-home-depot", k: ["home depot", "tools", "drill", "garden", "paint"] },
  { n: "Lowe's", s: "lowes", cb: "home-and-garden/lowes", k: ["lowes", "lowe's", "tools", "garden", "appliances"] },
  { n: "Nike", s: "nike", k: ["nike", "sneakers", "trainers", "shoes", "running", "sportswear"] },
  { n: "Foot Locker", s: "foot-locker", k: ["foot locker", "footlocker", "sneakers", "shoes", "trainers"] },
  { n: "Lululemon", s: "lululemon", k: ["lululemon", "yoga", "leggings", "sportswear"] },
  { n: "H&M", s: "hm", cb: "clothing/h-m", k: ["h&m", "hm", "clothes", "clothing", "dress", "jacket", "shirt", "jeans"] },
  { n: "ASOS", s: "asos", cb: "clothing/asos", k: ["asos", "clothes", "clothing", "dress", "jacket", "shoes", "jeans"] },
  { n: "Gap", s: "gap", cb: "clothing/gap", k: ["gap", "clothes", "clothing", "jeans", "shirt"] },
  { n: "Nordstrom", s: "nordstrom", cb: "clothing/nordstrom", k: ["nordstrom", "shoes", "handbag", "bag", "dress", "sunglasses", "leather"] },
  { n: "Macy's", s: "macys", cb: "clothing/macys", k: ["macys", "macy's", "handbag", "perfume", "dress", "jewelry"] },
  { n: "Sephora", s: "sephora-egift-card", cb: "health-spa-beauty/sephora", k: ["sephora", "makeup", "perfume", "cosmetics", "skincare", "fragrance"] },
  { n: "Ulta Beauty", s: "ulta-beauty", cb: "health-spa-beauty/ulta-beauty", k: ["ulta", "makeup", "cosmetics", "skincare", "hair"] },
  { n: "Steam", s: "steam", cb: "games/steam", k: ["steam", "game", "games", "gaming", "pc"] },
  { n: "PlayStation", s: "playstation", cb: "games/playstation", k: ["playstation", "ps5", "ps4", "psn", "game", "games", "gaming", "console"] },
  { n: "Xbox", s: "xbox", cb: "games/xbox-live", k: ["xbox", "game", "games", "gaming", "console"] },
  { n: "Nintendo", s: "nintendo", cb: "games/nintendo", k: ["nintendo", "switch", "game", "games", "gaming", "console"] },
  { n: "Epic Games", s: "epic-games", k: ["epic", "fortnite", "game", "games"] },
  { n: "Roblox", s: "roblox", cb: "games/roblox", k: ["roblox", "robux"] },
  { n: "Google Play", s: "google-play", cb: "entertainment/google-play", k: ["google play", "android", "apps"] },
  { n: "Netflix", s: "netflix", cb: "entertainment/netflix", k: ["netflix", "movies", "streaming", "tv"] },
  { n: "Spotify", s: "spotify", k: ["spotify", "music", "streaming", "podcasts"] },
  { n: "Airbnb", s: "airbnb", cb: "travel/airbnb", k: ["airbnb", "travel", "hotel", "apartment", "vacation", "trip"] },
  { n: "Hotels.com", s: "hotels-com", cb: "travel/hotels-com", k: ["hotels", "hotel", "travel", "vacation", "trip"] },
  { n: "Uber", s: "uber-rides", k: ["uber", "taxi", "ride", "rides"] },
  { n: "Uber Eats", s: "uber-uber-eats", cb: "foods-and-restaurants/uber-eats", k: ["uber eats", "food delivery", "delivery", "food"] },
  { n: "DoorDash", s: "doordash", cb: "foods-and-restaurants/doordash", k: ["doordash", "food delivery", "delivery", "food"] },
  { n: "Starbucks", s: "starbucks", k: ["starbucks", "coffee"] },
  { n: "Prepaid Visa", s: "prepaid-virtual-visa", k: ["visa", "prepaid", "card"] },
  { n: "Mastercard", s: "mastercard", k: ["mastercard", "prepaid", "card"] },
  { n: "NordVPN", s: "nordvpn", cb: "privacy-security/nordvpn", k: ["nordvpn", "vpn"] },
  // Coinsbee only (no CoinGate card found).
  { n: "Best Buy", cb: "electronics/best-buy", k: ["best buy", "bestbuy", "electronics", "tv", "laptop", "headphones", "camera"] },
  { n: "Adidas", cb: "sports-outdoors/adidas", k: ["adidas", "sneakers", "trainers", "shoes", "running", "sportswear"] },
  { n: "Zara", cb: "clothing/zara", k: ["zara", "clothes", "clothing", "dress", "jacket"] },
  { n: "IKEA", cb: "home-and-garden/ikea", k: ["ikea", "furniture", "sofa", "lamp", "desk"] },
  { n: "Wayfair", cb: "home-and-garden/wayfair", k: ["wayfair", "furniture", "sofa", "rug", "lamp"] },
];

export function giftCardsFor(query: string, max = 4): GiftCard[] {
  const q = query.toLowerCase().trim();
  if (!q) return [];
  // "pokemon cards", "Charizard card": collectible cards, not gift cards.
  if (/pok[eé]mon|tcg|trading card|charizard|booster|holo|1st edition|покемон|коллекц/.test(q)) return [];
  // A bare "card"/"cards" says nothing about a brand.
  const words = q.split(/\s+/).filter((w) => !/^(card|cards|карт[а-яё]*|карточ[а-яё]*)$/.test(w));
  const scored: [GiftCard, number][] = [];
  for (const g of GIFT_CARDS) {
    // Brand name hit ranks above a category hit ("nike shoes" → Nike first).
    let score = 0;
    for (const k of g.k) {
      const hit = k.includes(" ") ? q.includes(k) : words.includes(k);
      if (hit) score = Math.max(score, k === g.k[0] ? 2 : 1);
    }
    if (score) scored.push([g, score]);
  }
  return scored
    .sort((a, b) => b[1] - a[1])
    .slice(0, max)
    .map(([g]) => g);
}

export const giftUrl = (g: GiftCard) => (g.s ? GIFT_BASE + g.s + AFFILIATE : null);
export const cbUrl = (g: GiftCard) => (g.cb ? CB_BASE + g.cb + "/" + CB_AFFILIATE : null);
