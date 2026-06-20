export const SCHEMA_UNAVAILABLE_MESSAGE = "Schema indisponivel para esta selecao.";

export function getSchemaTables(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.tables)) return data.tables;
  if (Array.isArray(data?.schema?.tables)) return data.schema.tables;
  if (Array.isArray(data?.data?.tables)) return data.data.tables;

  return [];
}

export function isHtmlSchema(schema) {
  const text = String(schema == null ? "" : schema);
  return (
    /\bid=["']schema-data-table["']/.test(text) ||
    /\bclass=["'][^"']*\bcolumn-filter\b/.test(text)
  );
}

export function normalizeSchemaText(schema, fallback = SCHEMA_UNAVAILABLE_MESSAGE) {
  const text = String(schema == null ? "" : schema).trim();
  return text || fallback;
}
