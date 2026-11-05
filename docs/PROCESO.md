# Bible Adventures: proceso y estado (21-oct-2026)

Resumen de todo lo hecho, cómo se hace y qué queda pendiente, para retomar en otra sesión.

## 1. El juego

- **Motor:** Godot 4.7 (Forward+ en PC, Mobile en móvil). Abrir: `open -n -a /Applications/Godot.app --args --path .`
- **Capítulo 1 (El Arca de Noé):** isla con árboles, rocas, juncos y pozos de brea; recolección, fabricación (`data/recetas.json`), arca en 5 etapas (`data/arca.json`), textos de Génesis 6, guardado automático.
- **Arte:** Quaternius CC0 (animales, animaciones), shaders propios (viento, mar, madera, diorama, terreno), arca hecha por script en Blender.
- **Entorno: la aldea de Noé** (diseño en `docs/DISENO_CAPITULO1.md`, datos en `data/aldea.json`):
  - La distribución sale del [Village Generator de Watabou](https://watabou.github.io/village-generator/) (semilla 11, etiquetas `river,farmland,dense`, 420 × 315), exportada en JSON a `referencias/watabou_aldea11.json`. `herramientas/watabou_a_aldea.py` la escala (0,6) y la pasa a `data/aldea.json`: río, dos puentes, calles, plaza, 38 casas (el modelo según su forma), campos, huerto y árboles. Lo de la historia (casa de Noé y familia, prado del arca, cantera, brea, corrales, animales, camino al arca) va en `AJUSTES` dentro del script; no editar a mano lo que sale del generador. Con un tercer argumento dibuja una vista con el tamaño real de casas y patios:
    ```bash
    ~/herramientas/Hunyuan3D-2/.venv/bin/python herramientas/watabou_a_aldea.py referencias/watabou_aldea11.json data/aldea.json vista.png
    ```
    La aldea anterior, hecha a mano, quedó en `referencias/aldea_anterior.json`.
  - `scripts/world.gd`: valle con colinas alrededor, río con puentes, loma del arca, caminos curvos (Catmull-Rom) y sendas de cada puerta al camino más cercano, vegetación agrupada por reglas (orillas de caminos, pie de árboles, patios, manchas de prado). Las orillas de tierra las corta `shaders/terrain.gdshader`.
  - `scripts/village.gd`: casas mirando a la plaza, objetos en cada patio, pozo y bancos, corral y campos de trigo.
  - `herramientas/blender/casas.py` → `assets/aldea/aldea.glb`: casas de adobe (CasaNoe, CasaA/B/C, con contraventanas, cortinas y manchas de revoque), pozo, horno, banco, cántaro, cesta, leña, cerca, puesto, maceta, saco, alfombra, tendedero, telar, bebedero y la obra del arca (toldo, mesa de trabajo, caballetes, tablones, andamio, olla de brea; colocada en `SITE` de `scripts/ark_site.gd`):
    ```bash
    blender --background --factory-startup --python herramientas/blender/casas.py -- assets/aldea/aldea.glb
    ```
  - Objetos generados con IA: Hunyuan3D-2mini corre en local (`~/herramientas/Hunyuan3D-2`, servidor en
    `localhost:8081`; arrancar con `cd ~/herramientas/Hunyuan3D-2 && PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python api_server.py --host 127.0.0.1 --port 8081 --device mps`).
    Recortes de `referencias/objetos_aldea.jpg` en `referencias/recortes/`, formas en `herramientas/blender/generados/`,
    procesado (limpiar, escalar, reducir y pintar con los colores del recorte) con `herramientas/blender/procesar_generados.py`
    → `assets/aldea/generados.glb`. `scripts/piezas.gd` usa la versión generada de cada pieza cuando existe. Cada objeto tiene su archivo para retocarlo a mano en `herramientas/blender/objetos/<nombre>.blend` (versiones descartadas en `objetos/versiones/`); `herramientas/blender/exportar_objetos.py` los junta en el `.glb`. Los puestos del mercado se arman con `herramientas/blender/armar_puestos.py`: un puesto vacío y la mercancía generados por separado (`referencias/mercado_piezas.png`, piezas en `objetos/piezas_puesto/`); el toldo toma el color de cada puesto y las rayas las dibuja el shader. Pintado por materiales (el que mejor funciona): `herramientas/blender/vistas_gemini.py <objeto>` saca 4 vistas en gris (`referencias/vistas/`); Gemini pinta cada una con colores planos por material (prompt n.º 17, una por conversación; puede redibujarlas o ponerlas en espejo); se guardan como `vistas/<objeto>_<vista>_materiales.png` y `herramientas/blender/pintar_materiales.py <objeto>` las encaja solas, pinta el modelo detallado y hornea una textura limpia al ligero (lista de materiales en `MATERIALES`). La madera lleva un café común y veta dibujada con `shaders/props.gdshader` (`wood_color`).
  - `scripts/stylized.gd`: árboles, olivo, pinos, arbustos, flores, matas, trigo y rocas en paleta suave.
  - La isla tarda ~7 s en generarse (el mapa nuevo es unas tres veces más grande). Los modelos de naturaleza de Quaternius (`assets/naturaleza/`) ya no se usan.

## 2. Noé

**Noé actual (túnica corta, con piernas):** hoja de Gemini en T (prompt n.º 22, `referencias/noe_piernas_giro.webp`),
TRELLIS solo con la vista de frente (semilla 7) → `herramientas/blender/generados/noe_trellis/frente_s7.glb`,
`limpiar_trellis.py` (altura 1,5) → `assets/personajes/noe_trellis/noe_frente_s7.glb`, sin la franja de piel que TRELLIS
pintó en la falda (`limpiar_mancha_falda.py ... 0.35 0.62 0.34`), y rig:
```bash
blender --background --factory-startup --python herramientas/blender/rig_noe.py -- assets/personajes/noe_trellis/noe_frente_s7.glb assets/personajes/noe_trellis/noe_corta_rig.glb --perfil herramientas/blender/perfiles/noe_corta.json
```
Velocidades naturales (las imprime el rig) en `scripts/noah_rig.gd`; Noé va a `SPEED := 2.3`. La túnica larga
hecha aparte (`rig_noe_cadenas.py`, `falda_resortes.gd`, drapeada con la física de Blender) se probó y no quedó
bien: parecía un costal.

### Noé anterior (Rodin, túnica larga): cómo se hizo (cadena completa)

1. **Referencias** (`referencias/`): hoja de giro de Noé, cabeza, paleta, etc., generadas con Gemini a partir de `referencias/PROMPTS.md`.
2. **Modelo 3D con IA:** Hyper3D Rodin, enviando las 4 vistas de la hoja de giro (`condition_mode=concat`, tier Regular). Resultado: `assets/personajes/rodin/noe_rodin_original.glb` (98.000 triángulos). Coincidencia de silueta: 95 % de frente, 86 % en 3/
3. **Pulido** (`herramientas/blender/pulir_rodin.py`): sin aspecto metálico, colores llevados a la paleta, cuencas de los ojos rellenas (geometría, color y mapa de normales), ojos nuevos medio hundidos en la cara, rubor pintado.
4. **Reducción de polígonos:** 2.500 triángulos de cuerpo. Reparto automático por **grosor** (protege dedos, muñecas y nariz), prioridad extra opcional en hombros. El detalle original se hornea en un mapa de normales.
5. **Textura** (`herramientas/blender/textura.py`, pasos en orden):
   `paso_desplegar_pliegues` → `paso_cejas` → `paso_uv` → `paso_hornear` → `paso_pintar` → `paso_meter_pestana` → `paso_desplegar_pliegues` → `paso_uv` → `paso_hornear` → `paso_pintar` → `paso_hombros` → `paso_pintar` → `paso_exportar`.
   - Despliegue de textura sin triángulos superpuestos (los superpuestos se llevan a una franja aparte).
   - Pintado por partes con la paleta: cada triángulo es de una parte (pelo, piel, nariz, túnica, chaleco, manga, cuerda, sandalia), con reglas de posición en el cuerpo, abertura del chaleco recta, sandalias (suela + tira), trama de lino, oclusión suave.
   - Cejas como piezas aparte (medidas en `referencias/noe_cejas.json`).
   - Resultado: `assets/personajes/rodin/noe_juego.glb` (3.220 triángulos en total, 2,5 MB) y `noe_textura.blend` (+ `noe_textura_respaldo.blend`).
6. **Rig** (`herramientas/blender/rig_noe.py`, en segundo plano, ~2 min):
   ```bash
   blender --background --factory-startup --python herramientas/blender/rig_noe.py -- assets/personajes/rodin/noe_juego.glb assets/personajes/rodin/noe_rig.glb
   ```
   - Esqueleto de la Universal Animation Library (65 huesos) adaptado a las articulaciones de Noé.
   - Pesos automáticos + reglas: cabeza/barba/pelo rígidos con la cabeza, ropa del tronco solo con columna y piernas, falda mezclando pelvis y piernas, soga del cinto rígida con la pelvis (se detecta por su color en la textura).
   - 9 animaciones copiando la orientación de cada hueso (Idle, Walk, Jog_Fwd, Sprint, Interact, Sword_Attack, Fixing_Kneeling, PickUp_Table, Idle_Talking).
   - Imprime la velocidad natural de caminar/trotar/correr: copiarla en `scripts/noah_rig.gd` si cambian las proporciones.
7. **En el juego** (`scripts/noah_rig.gd`): carga `noe_rig.glb`; trote con 65 % de la inclinación de espalda y del braceo del original y sin vaivén de cadera; material mate al 74 % de luminosidad. Al talar lleva un hacha y al picar un pico en la mano derecha (piezas low poly hechas en código, pegadas al hueso `hand_r`; `GRIP_*` y `TOOL_TWIST` las colocan). Velocidad de Noé: `SPEED := 3.1` (trote Jog_Fwd; la túnica va con 8 cadenas de huesos de falda de `rig_noe.py`, movidas en el juego por resortes con colisión contra las piernas: `scripts/falda_resortes.gd`) en `scripts/player.gd`. Interpolación de física activada (quita el temblor a pantalla completa).

### La familia y los aldeanos con TRELLIS (gratis, lo que mejor funciona)

1. Hoja de giro en Gemini (prompt n.º 20, con la de Noé adjunta) **en T** (brazos horizontales, mangas
   separadas del cuerpo): con los brazos caídos, el generador une la manga con el costado y al caminar esa
   tela se estira. Gemini tiende a copiar la pose de la imagen adjunta: pedirla como hoja NUEVA, usando la
   anterior solo de referencia del diseño. Sus vistas de lado y espalda suelen salir mal en T: basta el frente.
2. TRELLIS en Hugging Face (Space `trellis-community/TRELLIS`, con la cuenta gratis ya conectada con
   `hf auth login`): primero se quita el fondo de cada vista (`/preprocess_image`) y luego las 4 vistas
   juntas en `/generate_and_extract_glb` con `multiimage_algo="multidiffusion"`. Sale con textura en ~30 s.
   Guardar en `herramientas/blender/generados/<nombre>_trellis/`.
3. `herramientas/blender/limpiar_trellis.py <trellis.glb> <salida.glb> <altura> <giro>`: une los pedazos,
   material mate (viene metálico), superficie suave, de pie y a su altura; si faltan tobillos, los pone.
4. Rig con `rig_noe.py` y su perfil (medidas de las articulaciones), y en `data/aldea.json` ("aldeanos")
   con `"brillo": 1.0`.

### La familia y los aldeanos pintando la forma local (descartado: se ve peor)

1. Hoja de giro en Gemini con la de Noé adjunta (prompt n.º 20 para la esposa) y la misma hoja recoloreada
   con un color puro por parte (prompt n.º 21). Las 4 vistas de cada una, recortadas justas, en
   `referencias/vistas_personajes/<nombre>_<vista>.png` y `<nombre>_partes_<vista>.png`.
2. Forma con Hunyuan3D en local (desde la vista de frente) → `herramientas/blender/generados/<nombre>.glb`.
3. `herramientas/blender/pintar_personaje.py`: encaja cada vista por su silueta, mira con un búfer de
   profundidad qué vistas ven cada punto, vota la parte con el mapa de colores puros, la limpia por parches
   (los pliegues de la ropa) y hornea una textura limpia en un modelo de 12.000 caras.
   ```bash
   blender --background --factory-startup --python herramientas/blender/pintar_personaje.py -- herramientas/blender/generados/esposa.glb esposa 1.45 assets/personajes/familia/esposa.glb
   ```
   Las partes y sus colores (`PARTES`, `PLANOS`) son los de la esposa: para otro personaje, cambiarlos.
4. Rig con el mismo script de Noé y un perfil de medidas (`herramientas/blender/perfiles/<nombre>.json`):
   ```bash
   blender --background --factory-startup --python herramientas/blender/rig_noe.py -- assets/personajes/familia/esposa.glb assets/personajes/familia/esposa_rig.glb --perfil herramientas/blender/perfiles/esposa.json
   ```
5. En el juego, `scripts/aldeano.gd` (datos en `data/aldea.json`, "aldeanos", que salen de
   `herramientas/watabou_a_aldea.py`): pasea despacio entre sus puntos del patio y en cada uno se queda
   de pie, hablando o trabajando.

### Para pasar tus ediciones de Blender al juego

1. En Blender: guardar la imagen de textura (Image → Save) y exportar `noe_juego.glb` (cuerpo `NoeLow2500`, ojos y cejas; "Selected Objects" y "Apply Modifiers").
2. Ejecutar el rig (comando de arriba).
3. Reimportar y abrir el juego. Solo el editor de Godot reimporta solo; si se abre el juego directamente
   (`godot --path .`), antes hay que ejecutar `godot --headless --import --path .` o seguirá el modelo viejo.

**Cuidado:** volver a ejecutar `paso_pintar` u otros pasos de `textura.py` reescribe la textura y borra lo pintado a mano.

## 3. Trabajar con Blender en vivo

- blender-mcp instalado (add-on activo, servidor en `localhost:9876`, se arranca al abrir Blender).
- `herramientas/blender/en_vivo.py` envía funciones de un script a la ventana abierta:
  `python3 herramientas/blender/en_vivo.py textura paso_pintar`
- Godot ignora los `.blend` (`import/blender/enabled=false` en `project.godot`).

## 4. Lecciones aprendidas (evitan horas de pruebas)

- **glTF separa los vértices en las costuras de la textura.** Al reimportar, unirlos (`remove_doubles`) antes de alisar o de poner pesos; si no, la malla se abre en grietas.
- **Triángulos superpuestos en la textura** hacen que una parte se pinte con el color de otra (manchas en las mangas). Comprobar siempre con `_overlapping_faces`.
- **Rotar aristas** (enderezar pliegues) estropea el despliegue de esos triángulos: después, repetir `paso_uv` + hornear + pintar.
- **El mapa de normales también "pinta" formas:** si se aplana la malla (ojos, cejas, hombros), aplanar también las normales en esa zona.
- **Cargar mallas desde un `.blend` lo deja abierto como biblioteca** y bloquea guardarlo: quitar la biblioteca después.
- **Ctrl + número en Blender añade suavizado** (subió los ojos a 46.000 triángulos). La exportación ahora avisa si el total pasa de 4.000.
- **Colores en Blender:** el pincel usa espacio lineal (sRGB^2.2).
- **Más polígonos no siempre ayuda:** en los hombros reaparece la pestaña del modelo de Rodin.

## 5. Pendiente

- Terminar los retoques a mano de la textura y pasarlos al juego (sección 2).
- Ver en el juego las acciones de talar, recoger y construir (solo revisadas en Blender).
- Facetas suaves en los tobillos; pestaña del hombro a revisar a mano.
- Licencia del modelo de Rodin (sección 2.2).
- Siguientes fases: animales que llegan al arca de dos en dos, controles táctiles para móvil, exportar a web/móvil (incluir `*.json` en la exportación).
