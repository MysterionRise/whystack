import { afterEach, describe, expect, it, vi } from "vitest";

import { hasDuplicateJsonValues } from "../src/contracts/generated";
import { parseUiEnvelope } from "../src/contracts/ui-envelope";

type JsonObject = Record<string, unknown>;

const CONTRACT_ERROR = {
  ok: false,
  error: { code: "invalid_ui_envelope" }
} as const;

function validEnvelope(): JsonObject {
  return {
    schemaVersion: "1.0",
    component: {
      kind: "recommendation-summary",
      id: "recommendation",
      title: "Demonstration recommendation",
      status: "demonstration",
      selectedOptionId: "option-a",
      rationale: "Option A has the highest deterministic fixture score.",
      optionScores: [
        { optionId: "option-a", score: 80 },
        { optionId: "option-b", score: 65 }
      ],
      disclaimer: "Demonstration output; no model provider was called."
    },
    actions: [
      {
        kind: "view-evidence",
        id: "view-evidence",
        label: "View evidence",
        enabled: false
      }
    ],
    meta: {
      runId: "01890f9a-7bcd-7abc-8def-0123456789ab",
      eventSequence: 3,
      generatedBy: "deterministic-fixture",
      fixtureVersion: "walking-skeleton-v1"
    }
  };
}

function cloneEnvelope(): JsonObject {
  return structuredClone(validEnvelope());
}

function component(payload: JsonObject): JsonObject {
  return payload.component as JsonObject;
}

function firstAction(payload: JsonObject): JsonObject {
  return (payload.actions as JsonObject[])[0];
}

function metadata(payload: JsonObject): JsonObject {
  return payload.meta as JsonObject;
}

function generatedInvalidEnvelopes(): Array<[string, unknown]> {
  const unknownVersion = cloneEnvelope();
  unknownVersion.schemaVersion = "2.0";

  const unknownKind = cloneEnvelope();
  component(unknownKind).kind = "arbitrary-html";

  const unknownField = cloneEnvelope();
  component(unknownField).unexpected = "closed-contract";

  const unknownAction = cloneEnvelope();
  firstAction(unknownAction).kind = "open-url";

  const markup = cloneEnvelope();
  component(markup).html = "<img src=x onerror=alert(1)>";

  const script = cloneEnvelope();
  component(script).script = "globalThis.compromised = true";

  const url = cloneEnvelope();
  firstAction(url).url = "https://attacker.invalid/collect";

  const route = cloneEnvelope();
  firstAction(route).route = "/invented-model-route";

  const prototype = cloneEnvelope();
  Object.defineProperty(prototype, "__proto__", {
    configurable: true,
    enumerable: true,
    value: { polluted: true }
  });

  const oversized = cloneEnvelope();
  component(oversized).rationale = "x".repeat(1201);

  const recursive = cloneEnvelope();
  recursive.recursive = recursive;

  return [
    ["unknown version", unknownVersion],
    ["unknown component kind", unknownKind],
    ["unknown field", unknownField],
    ["unknown action", unknownAction],
    ["markup field", markup],
    ["script field", script],
    ["URL-bearing action field", url],
    ["route-bearing action field", route],
    ["prototype field", prototype],
    ["oversized value", oversized],
    ["recursive value", recursive]
  ];
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("UiEnvelope closed contract", () => {
  it("keeps distinct nested JSON shapes separate during uniqueness checks", () => {
    const nestedThenSibling = { a: { b: 1 }, c: 2 };
    const nestedTogether = { a: { b: 1, c: 2 } };

    expect(
      hasDuplicateJsonValues([nestedThenSibling, nestedTogether])
    ).toBe(false);
    expect(
      hasDuplicateJsonValues([
        nestedThenSibling,
        structuredClone(nestedThenSibling)
      ])
    ).toBe(true);
  });

  it.each([
    [
      "throwing proxy",
      () =>
        new Proxy(
          {},
          {
            getPrototypeOf() {
              throw new Error("hostile proxy trap");
            }
          }
        )
    ],
    [
      "revoked proxy",
      () => {
        const revocable = Proxy.revocable({}, {});
        revocable.revoke();
        return revocable.proxy;
      }
    ]
  ])("returns the closed failure for a %s", (_name, makePayload) => {
    expect(parseUiEnvelope(makePayload())).toEqual(CONTRACT_ERROR);
  });

  it("rejects accessors without invoking untrusted getter code", () => {
    const payload = cloneEnvelope();
    const accessor = vi.fn(() => {
      throw new Error("untrusted getter executed");
    });
    Object.defineProperty(payload, "component", {
      enumerable: true,
      get: accessor
    });

    expect(parseUiEnvelope(payload)).toEqual(CONTRACT_ERROR);
    expect(accessor).not.toHaveBeenCalled();
  });

  it("accepts recommendation-summary@1.0", () => {
    const payload = validEnvelope();

    expect(parseUiEnvelope(payload)).toEqual({ ok: true, envelope: payload });
  });

  it.each([
    ["unknown component", (payload: JsonObject) => (component(payload).kind = "card")],
    ["unknown action", (payload: JsonObject) => (firstAction(payload).kind = "navigate")],
    ["extra property", (payload: JsonObject) => (payload.extra = true)],
    ["wrong version", (payload: JsonObject) => (payload.schemaVersion = "0.9")],
    ["malformed UUID", (payload: JsonObject) => (metadata(payload).runId = "not-a-uuid")],
    ["enabled evidence action", (payload: JsonObject) => (firstAction(payload).enabled = true)]
  ])("rejects %s", (_name, mutate) => {
    const payload = cloneEnvelope();
    mutate(payload);

    expect(parseUiEnvelope(payload)).toEqual(CONTRACT_ERROR);
  });

  it.each(generatedInvalidEnvelopes())(
    "fails closed for generated %s payloads without arbitrary execution",
    (_name, payload) => {
      const htmlExecution = vi.fn();
      const scriptExecution = vi.fn();
      const routeExecution = vi.fn();
      const networkExecution = vi.fn();
      vi.stubGlobal("document", {
        createElement: htmlExecution,
        write: htmlExecution
      });
      vi.stubGlobal("eval", scriptExecution);
      vi.stubGlobal("open", routeExecution);
      vi.stubGlobal("fetch", networkExecution);

      expect(parseUiEnvelope(payload)).toEqual(CONTRACT_ERROR);
      expect(htmlExecution).not.toHaveBeenCalled();
      expect(scriptExecution).not.toHaveBeenCalled();
      expect(routeExecution).not.toHaveBeenCalled();
      expect(networkExecution).not.toHaveBeenCalled();
    }
  );

  it("keeps approved text inert rather than interpreting it as executable input", () => {
    const payload = cloneEnvelope();
    component(payload).title = "<strong>Demonstration text</strong>";
    component(payload).rationale = "The string javascript:alert(1) remains text.";
    const htmlExecution = vi.fn();
    const scriptExecution = vi.fn();
    vi.stubGlobal("document", { write: htmlExecution });
    vi.stubGlobal("eval", scriptExecution);

    expect(parseUiEnvelope(payload)).toEqual({ ok: true, envelope: payload });
    expect(htmlExecution).not.toHaveBeenCalled();
    expect(scriptExecution).not.toHaveBeenCalled();
  });
});
