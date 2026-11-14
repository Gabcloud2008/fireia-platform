// Misión 016 — post-build robusto: copia .next/static y public dentro del
// servidor standalone que genera Next (útil para el despliegue portable).
// La ruta del standalone depende del layout del workspace, por eso se
// descubre dinámicamente en lugar de hardcodearla (M016: fix del cp).
import { cpSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { join } from "node:path";

const standalone = join(process.cwd(), ".next", "standalone");

function buscarDirWeb(dir) {
  // server.js puede quedar en la raíz de standalone (cuando Next detecta el
  // proyecto como raíz) o anidado según el layout del workspace: se busca
  // en ambos lugares.
  if (existsSync(join(dir, "server.js"))) return dir;
  for (const nombre of readdirSync(dir, { withFileTypes: true })) {
    if (!nombre.isDirectory() || nombre.name === "node_modules") continue;
    const ruta = join(dir, nombre.name);
    const anidado = buscarDirWeb(ruta);
    if (anidado) return anidado;
  }
  return null;
}

if (!existsSync(standalone)) {
  console.log("[postbuild] sin standalone (output no standalone): nada que copiar");
  process.exit(0);
}
const destino = buscarDirWeb(standalone);
if (!destino) {
  console.error("[postbuild] no se encontró server.js dentro de .next/standalone");
  process.exit(1);
}
mkdirSync(join(destino, ".next"), { recursive: true });
cpSync(join(process.cwd(), ".next", "static"), join(destino, ".next", "static"), { recursive: true });
cpSync(join(process.cwd(), "public"), destino, { recursive: true });
console.log(`[postbuild] standalone listo en ${destino}`);
