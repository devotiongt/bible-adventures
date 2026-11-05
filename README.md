# Bible Adventures · Capítulo 1: El Arca de Noé

Proceso completo, estado y pendientes: [docs/PROCESO.md](docs/PROCESO.md).

Juego low poly de exploración, recolección y construcción hecho con **Godot 4.7**. Usa el renderizador *Forward+* en PC y Mac y *Mobile* en teléfonos.

## Jugar

En Mac, doble clic en **Jugar.command** (reimporta los modelos nuevos y abre el juego). Desde la terminal:

```bash
godot --path .
```

O abre la carpeta en el editor de Godot y pulsa ▶.

| Acción | Teclado | Mando |
|---|---|---|
| Moverse | WASD / flechas | Stick izquierdo |
| Acción (talar, recoger, construir) | E / Espacio (mantener para repetir) | A |
| Panel de fabricación | C / Tab | Y |
| Girar cámara | Q / R, o arrastrar con clic derecho | LB / RB |
| Zoom | Rueda del ratón | — |
| Reiniciar partida | F9 | — |

## Bucle de juego

1. Tala árboles (madera), recoge juncos (fibra) y pica rocas (piedra).
2. Fabrica cuerda y un **martillo**, que hace falta para construir.
3. Construye el arca en 5 etapas: quilla, casco, sellado con brea (necesitas un **cubo**), cubiertas y techo con puerta.
4. Cada etapa muestra un pasaje de Génesis 6.

## Estructura

- `data/`: objetos, recetas y etapas del arca en JSON. Se pueden ajustar o ampliar sin tocar código.
- `scripts/game_state.gd`: autoload `Game` con el inventario, la fabricación, el arca, los controles y el guardado.
- `scripts/world.gd`: genera la isla (terreno, mar, hierba, vegetación, recursos y nubes).
- `scripts/resource_node.gd`: árboles, rocas, juncos y pozos de brea.
- `scripts/ark_site.gd`: el arca por etapas (modelo de Blender), con un "fantasma" de la siguiente y colisión real.
- `scripts/player.gd` y `scripts/camera_rig.gd`: Noé y la cámara.
- `scripts/hud.gd`: la interfaz.
- `scripts/noah_rig.gd`: Noé del juego (modelo de Rodin pulido y riggeado) con sus animaciones. `noah_model.gd` es la versión anterior, ya sin usar.
- `scripts/robe_cloth.gd`: falda simulada como tela (inercia, gravedad y choque con las piernas) que deforma la falda con pliegues hecha en Blender.
- `scripts/animal.gd`: animales de ambiente.
- `scripts/models.gd` y `scripts/effects.gd`: carga de modelos, viento y partículas.
- `shaders/`: viento en hojas y hierba, mar, madera del arca, pelo canoso y efecto diorama.
- `scripts/debug.gd`: pruebas automáticas y capturas de pantalla.

## Modelos hechos en Blender

El arca y la ropa de Noé se generan con scripts de Blender, así se pueden retocar y regenerar:

```bash
blender --background --factory-startup --python herramientas/blender/arca.py -- assets/arca/arca.glb
```

```bash
blender --background --factory-startup --python herramientas/blender/tunica.py -- assets/personajes/tunica.glb
```

Añade una carpeta como segundo argumento para guardar renders. Las medidas están al principio de cada script.

- [arca.py](herramientas/blender/arca.py): casco de tablones curvos, cuadernas, cubierta, aposentos, techo, puerta y rampa; un objeto por etapa.
- [tunica.py](herramientas/blender/tunica.py): adelgaza el cuerpo base (que es de "superhéroe"), saca la túnica del propio cuerpo (ajustada, sin capas y con sus mismos pesos) con el manto y la faja como zonas de color, y crea la falda con pliegues que mueve la simulación de tela.

**Verlo en vivo:** con Blender abierto, [en_vivo.py](herramientas/blender/en_vivo.py) envía un script paso a paso al add-on blender-mcp y la escena se va construyendo en la ventana:

```bash
python3 herramientas/blender/en_vivo.py tunica paso_importar paso_adelgazar paso_tunica paso_nudo paso_falda --pausa 2
```

El proyecto también registra [blender-mcp](https://github.com/ahujasid/blender-mcp) en `.mcp.json`: con Blender abierto, Claude Code puede modelar directamente en la escena (el add-on arranca su servidor al abrir Blender).

### Noé: de la edición al juego

1. Editar en Blender `assets/personajes/rodin/noe_textura.blend` (forma y textura).
2. Guardar la imagen de la textura (Image → Save) y exportar `noe_juego.glb` (cuerpo, ojos y cejas).
3. Riggear y pasar animaciones (en segundo plano, unos 2 minutos):

```bash
blender --background --factory-startup --python herramientas/blender/rig_noe.py -- assets/personajes/rodin/noe_juego.glb assets/personajes/rodin/noe_rig.glb
```

El juego carga `noe_rig.glb`. El script imprime la velocidad natural de caminar y trotar; si cambian las proporciones, actualízalas en `scripts/noah_rig.gd`.

## Créditos de arte

Modelos 3D de [Quaternius](https://quaternius.com) con licencia CC0 (dominio público), en `assets/`:
- Stylized Nature MegaKit (árboles, rocas, plantas, hierba).
- Ultimate Animated Animal Pack.
- Universal Base Characters y Universal Animation Library.

## Pruebas

```bash
godot --headless --path . -- --sin_guardar --nuevo --sin_intro --autotest
```

Argumentos útiles tras `--`:
- `--nuevo`: empieza una partida nueva.
- `--sin_guardar`: no toca la partida guardada.
- `--demo`: llena el inventario.
- `--etapas=N`: arranca con N etapas del arca construidas.
- `--pos=x,z`: coloca a Noé en ese punto.
- `--zoom=N`: distancia de la cámara.
- `--captura=archivo.png`: guarda una captura y cierra el juego.
- `--sin_diorama`, `--sin_glow`, `--sin_ssao`: desactivan efectos para comparar.
- `--caminar=0.3`: hace caminar a Noé (1 = trotar) durante la captura. Con `--dir=mover_der`, `--giro=1.9` y `--dir2=mover_izq` cambia de dirección a mitad de camino.
