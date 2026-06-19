import { describe, expect, it } from "vitest";

import { getSchemaTables, isHtmlSchema, normalizeSchemaText } from "./schema-utils";

describe("schema-utils", () => {
  it("returns schema table names from common response shapes", () => {
    expect(getSchemaTables({ tables: ["tb_cid", "tb_municipio"] })).toEqual(["tb_cid", "tb_municipio"]);
    expect(getSchemaTables({ schema: { tables: ["tb_procedimento"] } })).toEqual(["tb_procedimento"]);
    expect(getSchemaTables({})).toEqual([]);
  });

  it("detects HTML schemas with sample data or schema table markup", () => {
    expect(isHtmlSchema('<div class="sample-data-table"><table></table></div>')).toBe(true);
    expect(isHtmlSchema('<table class="schema-table"></table>')).toBe(true);
    expect(isHtmlSchema("CREATE TABLE tb_cid (id text);")).toBe(false);
  });

  it("normalizes empty schema text to the unavailable message", () => {
    expect(normalizeSchemaText("")).toBe("Schema indisponivel para esta selecao.");
    expect(normalizeSchemaText(null)).toBe("Schema indisponivel para esta selecao.");
    expect(normalizeSchemaText("  CREATE TABLE tb_cid (id text);  ")).toBe("CREATE TABLE tb_cid (id text);");
  });
});
