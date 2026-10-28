// Copies the barcode reader's WebAssembly (zxing-wasm, used by the scanner where the
// browser has no BarcodeDetector of its own, e.g. on iPhones) next to the static files.
// The scanner loads it from this origin: the Content-Security-Policy allows nothing else.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const source = require.resolve("zxing-wasm/reader/zxing_reader.wasm");
mkdirSync("public/zxing", { recursive: true });
copyFileSync(source, "public/zxing/zxing_reader.wasm");
