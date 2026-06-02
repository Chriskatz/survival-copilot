const DEFAULT_MAX_BYTES = 200;
const HEADER_RESERVE = 8;

const enc = new TextEncoder();
const dec = new TextDecoder("utf-8", { fatal: false });

export interface ChunkOptions {
  maxBytes?: number;
}

export function chunkForMesh(text: string, opts: ChunkOptions = {}): string[] {
  const maxBytes = opts.maxBytes ?? DEFAULT_MAX_BYTES;
  if (maxBytes <= HEADER_RESERVE) {
    throw new Error(`maxBytes must exceed header reserve (${HEADER_RESERVE})`);
  }

  const bodyMax = maxBytes - HEADER_RESERVE;
  const bodies = packByByteBudget(text, bodyMax);
  const total = bodies.length || 1;

  return bodies.map((body, i) => `[${i + 1}/${total}] ${body}`);
}

function packByByteBudget(text: string, maxBytes: number): string[] {
  const bytes = enc.encode(text);
  if (bytes.length === 0) return [""];

  const chunks: string[] = [];
  let offset = 0;

  while (offset < bytes.length) {
    let end = Math.min(offset + maxBytes, bytes.length);
    while (end > offset && end < bytes.length && isUtf8Continuation(bytes[end])) {
      end--;
    }
    chunks.push(dec.decode(bytes.subarray(offset, end)));
    offset = end;
  }

  return chunks;
}

function isUtf8Continuation(byte: number | undefined): boolean {
  return byte !== undefined && (byte & 0xc0) === 0x80;
}

export function byteLength(s: string): number {
  return enc.encode(s).length;
}
