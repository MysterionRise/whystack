import { createHash } from "node:crypto";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = resolve(SCRIPT_DIRECTORY, "../../..");
const OPENAPI_PATH = resolve(REPOSITORY_ROOT, "contracts/generated/openapi.json");
const UI_SCHEMA_PATH = resolve(
  REPOSITORY_ROOT,
  "contracts/generated/ui-envelope.schema.json"
);
const OUTPUT_PATH = resolve(
  REPOSITORY_ROOT,
  "apps/web/src/contracts/generated.ts"
);

const SCHEMA_KEYS = new Set([
  "$defs",
  "$id",
  "$ref",
  "$schema",
  "additionalProperties",
  "allOf",
  "anyOf",
  "const",
  "default",
  "description",
  "discriminator",
  "enum",
  "examples",
  "exclusiveMaximum",
  "exclusiveMinimum",
  "format",
  "items",
  "maxItems",
  "maxLength",
  "maximum",
  "minItems",
  "minLength",
  "minimum",
  "not",
  "oneOf",
  "pattern",
  "properties",
  "readOnly",
  "required",
  "title",
  "type",
  "uniqueItems"
]);
const UNSUPPORTED_RUNTIME_ASSERTION_KEYS = new Set([
  "exclusiveMaximum",
  "exclusiveMinimum",
  "not"
]);

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requireRecord(value, location) {
  if (!isRecord(value)) {
    throw new Error(`${location} must be an object`);
  }
  return value;
}

function validateSchema(value, location, runtimeSchema = false) {
  const schema = requireRecord(value, location);
  for (const key of Object.keys(schema)) {
    if (!SCHEMA_KEYS.has(key)) {
      throw new Error(`unsupported JSON Schema keyword ${location}.${key}`);
    }
    if (runtimeSchema && UNSUPPORTED_RUNTIME_ASSERTION_KEYS.has(key)) {
      throw new Error(
        `unsupported runtime JSON Schema assertion ${location}.${key}`
      );
    }
  }

  for (const keyword of ["allOf", "anyOf", "oneOf"]) {
    if (keyword in schema) {
      if (!Array.isArray(schema[keyword])) {
        throw new Error(`${location}.${keyword} must be an array`);
      }
      schema[keyword].forEach((item, index) =>
        validateSchema(item, `${location}.${keyword}[${index}]`, runtimeSchema)
      );
    }
  }

  for (const keyword of ["$defs", "properties"]) {
    if (keyword in schema) {
      const entries = requireRecord(schema[keyword], `${location}.${keyword}`);
      for (const [name, item] of Object.entries(entries)) {
        validateSchema(item, `${location}.${keyword}.${name}`, runtimeSchema);
      }
    }
  }

  if (isRecord(schema.items)) {
    validateSchema(schema.items, `${location}.items`, runtimeSchema);
  }
  if (isRecord(schema.additionalProperties)) {
    validateSchema(
      schema.additionalProperties,
      `${location}.additionalProperties`,
      runtimeSchema
    );
  }
  if (isRecord(schema.not)) {
    validateSchema(schema.not, `${location}.not`, runtimeSchema);
  }
  return schema;
}

function verifyRuntimeAssertionPolicy() {
  const cases = [
    ["exclusiveMaximum", { type: "number", exclusiveMaximum: 1 }],
    ["exclusiveMinimum", { type: "number", exclusiveMinimum: 0 }],
    ["not", { type: "string", not: { const: "forbidden" } }]
  ];
  for (const [keyword, schema] of cases) {
    validateSchema(schema, `OpenAPI compatibility self-check ${keyword}`);
    try {
      validateSchema(schema, `runtime policy self-check ${keyword}`, true);
    } catch (error) {
      if (
        error instanceof Error &&
        error.message ===
          `unsupported runtime JSON Schema assertion runtime policy self-check ${keyword}.${keyword}`
      ) {
        continue;
      }
      throw error;
    }
    throw new Error(`runtime schema policy accepted unsupported ${keyword}`);
  }
}

function literal(value) {
  const rendered = JSON.stringify(value);
  if (rendered === undefined) {
    throw new Error("contract literals must be JSON values");
  }
  return rendered;
}

function referenceName(reference, prefix) {
  if (typeof reference !== "string" || !reference.startsWith(prefix)) {
    throw new Error(`unsupported contract reference ${String(reference)}`);
  }
  const name = decodeURIComponent(reference.slice(prefix.length));
  if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name)) {
    throw new Error(`unsafe contract reference name ${name}`);
  }
  return name;
}

function renderObjectType(schema, level) {
  const properties = isRecord(schema.properties) ? schema.properties : {};
  const required = new Set(Array.isArray(schema.required) ? schema.required : []);
  const additional = schema.additionalProperties;
  const additionalType = isRecord(additional)
    ? renderType(additional, level + 1)
    : "unknown";
  const names = new Set([...Object.keys(properties), ...required]);
  const indentation = "  ".repeat(level + 1);
  const closing = "  ".repeat(level);
  const fields = [...names].sort().map((name) => {
    const property = properties[name];
    const propertyType = property
      ? renderType(requireRecord(property, `property ${name}`), level + 1)
      : additionalType;
    return `${indentation}${JSON.stringify(name)}${required.has(name) ? "" : "?"}: ${propertyType};`;
  });

  if (additional === true || isRecord(additional)) {
    fields.push(`${indentation}[key: string]: ${additionalType};`);
  }
  if (fields.length === 0) {
    return additional === false ? "Record<string, never>" : "Record<string, unknown>";
  }
  return `{\n${fields.join("\n")}\n${closing}}`;
}

function renderType(schema, level = 0) {
  if ("$ref" in schema) {
    return referenceName(schema.$ref, "#/components/schemas/");
  }
  if (Object.hasOwn(schema, "const")) {
    return literal(schema.const);
  }
  if (Array.isArray(schema.enum)) {
    return schema.enum.map(literal).join(" | ");
  }
  for (const [keyword, separator] of [
    ["oneOf", " | "],
    ["anyOf", " | "],
    ["allOf", " & "]
  ]) {
    if (Array.isArray(schema[keyword])) {
      return schema[keyword]
        .map((item) => `(${renderType(requireRecord(item, keyword), level)})`)
        .join(separator);
    }
  }
  if (Array.isArray(schema.type)) {
    return schema.type.map((type) => renderType({ type }, level)).join(" | ");
  }
  switch (schema.type) {
    case "array":
      return `Array<${renderType(requireRecord(schema.items, "array items"), level + 1)}>`;
    case "boolean":
      return "boolean";
    case "integer":
    case "number":
      return "number";
    case "null":
      return "null";
    case "object":
      return renderObjectType(schema, level);
    case "string":
      return "string";
    case undefined:
      return "unknown";
    default:
      throw new Error(`unsupported JSON Schema type ${String(schema.type)}`);
  }
}

function schemaVariable(name) {
  return `${name[0].toLowerCase()}${name.slice(1)}Schema`;
}

function uiReferenceVariable(reference) {
  return schemaVariable(referenceName(reference, "#/$defs/"));
}

function renderZodEnum(values) {
  if (values.length === 0) {
    throw new Error("contract enum must contain at least one value");
  }
  const members = values.map((value) => `z.literal(${literal(value)})`);
  return members.length === 1 ? members[0] : `z.union([${members.join(", ")}])`;
}

function renderZodObject(schema, level) {
  const properties = requireRecord(schema.properties ?? {}, "object properties");
  const required = new Set(Array.isArray(schema.required) ? schema.required : []);
  const indentation = "  ".repeat(level + 1);
  const closing = "  ".repeat(level);
  const entries = Object.entries(properties)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([name, property]) => {
      let validator = renderZod(requireRecord(property, `property ${name}`), level + 1);
      if (!required.has(name)) {
        validator += ".optional()";
      }
      return `${indentation}${JSON.stringify(name)}: ${validator}`;
    });
  let rendered = `z.object({\n${entries.join(",\n")}\n${closing}})`;
  if (schema.additionalProperties === false) {
    rendered += ".strict()";
  } else if (isRecord(schema.additionalProperties)) {
    rendered += `.catchall(${renderZod(schema.additionalProperties, level)})`;
  } else {
    rendered += ".passthrough()";
  }
  return rendered;
}

function renderZod(schema, level = 0) {
  if ("$ref" in schema) {
    return uiReferenceVariable(schema.$ref);
  }
  if (Object.hasOwn(schema, "const")) {
    return `z.literal(${literal(schema.const)})`;
  }
  if (Array.isArray(schema.enum)) {
    return renderZodEnum(schema.enum);
  }
  for (const keyword of ["oneOf", "anyOf"]) {
    if (Array.isArray(schema[keyword])) {
      const alternatives = schema[keyword].map((item) =>
        renderZod(requireRecord(item, keyword), level)
      );
      if (alternatives.length < 2) {
        return alternatives[0];
      }
      return `z.union([${alternatives.join(", ")}])`;
    }
  }
  if (Array.isArray(schema.allOf)) {
    const intersections = schema.allOf.map((item) =>
      renderZod(requireRecord(item, "allOf"), level)
    );
    if (intersections.length === 0) {
      throw new Error("allOf must contain at least one schema");
    }
    return intersections.slice(1).reduce((left, right) => `${left}.and(${right})`, intersections[0]);
  }

  let rendered;
  switch (schema.type) {
    case "array": {
      rendered = `z.array(${renderZod(requireRecord(schema.items, "array items"), level)})`;
      if (Number.isInteger(schema.minItems)) {
        rendered += `.min(${schema.minItems})`;
      }
      if (Number.isInteger(schema.maxItems)) {
        rendered += `.max(${schema.maxItems})`;
      }
      if (schema.uniqueItems === true) {
        rendered +=
          ".superRefine((items, context) => { if (hasDuplicateJsonValues(items)) { context.addIssue({ code: z.ZodIssueCode.custom, message: \"array items must be unique\" }); } })";
      }
      return rendered;
    }
    case "boolean":
      return "z.boolean()";
    case "integer":
      rendered = "z.number().finite().int()";
      break;
    case "number":
      rendered = "z.number().finite()";
      break;
    case "object":
      return renderZodObject(schema, level);
    case "string":
      rendered = "z.string()";
      if (schema.format === "uuid") {
        rendered += ".uuid()";
      }
      if (typeof schema.pattern === "string") {
        rendered += `.regex(new RegExp(${literal(schema.pattern)}))`;
      }
      if (Number.isInteger(schema.minLength)) {
        rendered += `.refine((value) => Array.from(value).length >= ${schema.minLength}, \"string is too short\")`;
      }
      if (Number.isInteger(schema.maxLength)) {
        rendered += `.refine((value) => Array.from(value).length <= ${schema.maxLength}, \"string is too long\")`;
      }
      return rendered;
    default:
      throw new Error(`unsupported runtime JSON Schema type ${String(schema.type)}`);
  }

  if (typeof schema.minimum === "number") {
    rendered += `.min(${schema.minimum})`;
  }
  if (typeof schema.maximum === "number") {
    rendered += `.max(${schema.maximum})`;
  }
  return rendered;
}

function definitionOrder(definitions) {
  const ordered = [];
  const complete = new Set();
  const active = new Set();

  function visit(name) {
    if (complete.has(name)) {
      return;
    }
    if (active.has(name)) {
      throw new Error(`recursive runtime schema definition ${name} is unsupported`);
    }
    const schema = requireRecord(definitions[name], `UI definition ${name}`);
    active.add(name);
    const visitReferences = (value) => {
      if (Array.isArray(value)) {
        value.forEach(visitReferences);
      } else if (isRecord(value)) {
        if (typeof value.$ref === "string" && value.$ref.startsWith("#/$defs/")) {
          visit(referenceName(value.$ref, "#/$defs/"));
        }
        Object.values(value).forEach(visitReferences);
      }
    };
    visitReferences(schema);
    active.delete(name);
    complete.add(name);
    ordered.push(name);
  }

  Object.keys(definitions).sort().forEach(visit);
  return ordered;
}

function digest(content) {
  return createHash("sha256").update(content).digest("hex");
}

function renderGenerated(openApiText, uiSchemaText) {
  verifyRuntimeAssertionPolicy();
  const openApi = requireRecord(JSON.parse(openApiText), "OpenAPI document");
  const components = requireRecord(openApi.components, "OpenAPI components");
  const schemas = requireRecord(components.schemas, "OpenAPI component schemas");
  const uiSchema = validateSchema(JSON.parse(uiSchemaText), "UI schema", true);
  for (const [name, schema] of Object.entries(schemas)) {
    validateSchema(schema, `OpenAPI component ${name}`);
  }

  const typeDeclarations = Object.entries(schemas)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([name, schema]) => `export type ${name} = ${renderType(schema)};`)
    .join("\n\n");

  const definitions = requireRecord(uiSchema.$defs, "UI schema definitions");
  const runtimeDefinitions = definitionOrder(definitions)
    .map((name) => {
      const schema = requireRecord(definitions[name], `UI definition ${name}`);
      return `const ${schemaVariable(name)} = ${renderZod(schema)};`;
    })
    .join("\n\n");
  const rootSchema = { ...uiSchema };
  delete rootSchema.$defs;

  return `// Generated by apps/web/scripts/generate-contracts.mjs. Do not edit.\n// OpenAPI SHA-256: ${digest(openApiText)}\n// UI Schema SHA-256: ${digest(uiSchemaText)}\n\nimport { z } from "zod";\n\n${typeDeclarations}\n\nfunction canonicalJson(value: unknown): string {\n  if (Array.isArray(value)) {\n    return \`[\${value.map(canonicalJson).join(",")}]\`;\n  }\n  if (value !== null && typeof value === "object") {\n    const record = value as Record<string, unknown>;\n    const entries = Object.keys(record)\n      .sort()\n      .map((key) => \`\${JSON.stringify(key)}:\${canonicalJson(record[key])}\`);\n    return \`{\${entries.join(",")}}\`;\n  }\n  return JSON.stringify(value) ?? "undefined";\n}\n\nexport function hasDuplicateJsonValues(values: readonly unknown[]): boolean {\n  const identities = values.map(canonicalJson);\n  return new Set(identities).size !== identities.length;\n}\n\n${runtimeDefinitions}\n\nexport const uiEnvelopeSchema = ${renderZod(rootSchema)};\n\nexport type UiEnvelopeRuntime = z.infer<typeof uiEnvelopeSchema>;\n`;
}

async function main() {
  const mode = process.argv[2];
  if ((mode !== "--write" && mode !== "--check") || process.argv.length !== 3) {
    throw new Error("usage: generate-contracts.mjs --write|--check");
  }
  const [openApiText, uiSchemaText] = await Promise.all([
    readFile(OPENAPI_PATH, "utf8"),
    readFile(UI_SCHEMA_PATH, "utf8")
  ]);
  const generated = renderGenerated(openApiText, uiSchemaText);

  if (mode === "--write") {
    await mkdir(dirname(OUTPUT_PATH), { recursive: true });
    await writeFile(OUTPUT_PATH, generated, "utf8");
    process.stdout.write(`generated ${OUTPUT_PATH}\n`);
    return;
  }

  let current;
  try {
    current = await readFile(OUTPUT_PATH, "utf8");
  } catch {
    current = "";
  }
  if (current !== generated) {
    process.stderr.write(`frontend contract drift: ${OUTPUT_PATH}\n`);
    process.exitCode = 1;
    return;
  }
  process.stdout.write(`current ${OUTPUT_PATH}\n`);
}

await main();
