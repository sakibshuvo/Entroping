const configuredBase = import.meta.env.BASE_URL;
const normalizedBase = configuredBase.endsWith("/")
  ? configuredBase
  : `${configuredBase}/`;

export function withBase(path = ""): string {
  const relativePath = path.startsWith("/") ? path.slice(1) : path;
  return `${normalizedBase}${relativePath}`;
}
