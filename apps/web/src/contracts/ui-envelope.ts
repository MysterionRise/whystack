import { uiEnvelopeSchema, type UiEnvelope } from "./generated";

export type UiEnvelopeContractError = {
  readonly code: "invalid_ui_envelope";
};

export type UiEnvelopeParseResult =
  | { readonly ok: true; readonly envelope: UiEnvelope }
  | { readonly ok: false; readonly error: UiEnvelopeContractError };

const MAX_CONTAINER_ENTRIES = 128;
const MAX_NESTING_DEPTH = 32;
const FORBIDDEN_KEYS = new Set(["__proto__", "constructor", "prototype"]);

function isSafeJsonValue(
  value: unknown,
  seen: WeakSet<object>,
  depth: number
): boolean {
  if (depth > MAX_NESTING_DEPTH) {
    return false;
  }
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean"
  ) {
    return true;
  }
  if (typeof value === "number") {
    return Number.isFinite(value);
  }
  if (typeof value !== "object" || seen.has(value)) {
    return false;
  }
  seen.add(value);

  if (Array.isArray(value)) {
    if (
      Object.getPrototypeOf(value) !== Array.prototype ||
      value.length > MAX_CONTAINER_ENTRIES
    ) {
      return false;
    }
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const keys = Reflect.ownKeys(descriptors);
    if (keys.some((key) => typeof key !== "string")) {
      return false;
    }
    for (let index = 0; index < value.length; index += 1) {
      const descriptor = descriptors[String(index)];
      if (
        descriptor === undefined ||
        !("value" in descriptor) ||
        !descriptor.enumerable ||
        !isSafeJsonValue(descriptor.value, seen, depth + 1)
      ) {
        return false;
      }
    }
    return keys.every(
      (key) => key === "length" || /^(?:0|[1-9][0-9]*)$/.test(String(key))
    );
  }

  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    return false;
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.length > MAX_CONTAINER_ENTRIES) {
    return false;
  }
  for (const key of keys) {
    if (typeof key !== "string" || FORBIDDEN_KEYS.has(key)) {
      return false;
    }
    const descriptor = descriptors[key];
    if (
      !("value" in descriptor) ||
      !descriptor.enumerable ||
      !isSafeJsonValue(descriptor.value, seen, depth + 1)
    ) {
      return false;
    }
  }
  return true;
}

function contractError(): UiEnvelopeParseResult {
  return { ok: false, error: { code: "invalid_ui_envelope" } };
}

export function parseUiEnvelope(input: unknown): UiEnvelopeParseResult {
  try {
    if (!isSafeJsonValue(input, new WeakSet(), 0)) {
      return contractError();
    }
    const parsed = uiEnvelopeSchema.safeParse(input);
    if (!parsed.success) {
      return contractError();
    }
    return { ok: true, envelope: parsed.data };
  } catch {
    return contractError();
  }
}
