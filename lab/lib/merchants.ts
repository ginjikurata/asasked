import data from "./merchants.json";

export type Merchant = {
  name: string;
  domain: string;
  url: string;
  category: string;
  group: string;
  kind: string;
  payment: string;
  gateway: string;
  network: string;
  status: "yes" | "partial";
  checked: string | null;
  how: string;
};

export const MERCHANTS = data as Merchant[];

export const STATUS_LABEL: Record<Merchant["status"], string> = {
  yes: "Checked",
  partial: "Partly checked",
};

export const STATUS_HELP: Record<Merchant["status"], string> = {
  yes: "We saw crypto or stablecoin payment on the store's own site. The date is the last time we saw it.",
  partial:
    "A payment provider lists the store, or the site mentions crypto, but we could not see the payment option ourselves.",
};

export const KIND_LABEL: Record<string, string> = {
  online: "Online",
  digital: "Digital goods",
  in_store: "In store",
};

export function lastChecked(): string | null {
  return MERCHANTS.map((m) => m.checked).filter(Boolean).sort().at(-1) ?? null;
}
