const MAX_BALANCE_FEN = 2_147_483_647;

/** UUID v4 also works on existing HTTP deployments, where randomUUID is unavailable. */
export function createAdjustmentRequestId(): string {
  if (typeof globalThis.crypto.randomUUID === "function") return globalThis.crypto.randomUUID();
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function buildBalanceAdjustment(
  amount: string,
  direction: "increase" | "decrease",
  currentBalance: number,
  note: string,
  requestId: string,
) {
  const raw = amount.trim();
  const amountFen = Math.round(Number(raw) * 100);
  if (!/^\d+(\.\d{1,2})?$/.test(raw) || !Number.isSafeInteger(amountFen) || amountFen <= 0) {
    throw new Error("请输入大于 0 的金额，最多保留两位小数");
  }
  if (!note.trim()) throw new Error("请填写调账原因，以便追溯本次操作");
  if (note.trim().length > 255) throw new Error("调账原因最多 255 个字符");
  const delta = direction === "decrease" ? -amountFen : amountFen;
  if (currentBalance + delta < 0) throw new Error("减少后余额不能为负");
  if (amountFen > MAX_BALANCE_FEN || currentBalance + delta > MAX_BALANCE_FEN) {
    throw new Error("单次调账金额与调整后余额均不能超过 ¥21,474,836.47");
  }
  return {
    balance_delta_fen: delta,
    balance_note: note.trim(),
    balance_request_id: requestId,
    expected_balance_fen: currentBalance,
  };
}
