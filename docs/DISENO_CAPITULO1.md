# Capítulo 1: la aldea de Noé (diseño)

Diseño del entorno del capítulo 1. Sustituye la isla generada al azar por una aldea diseñada a mano,
*cute* y *cozy*.

**Decidido (21-oct-2026):** valle con río (sin mar); la esposa de Noé no lleva nombre (fiel al
texto); primero la aldea y el terreno, después los personajes. Todo debe sentirse **orgánico**:
curvas suaves y cosas donde tienen sentido, nunca dispersión al azar.

## 1. Idea

Noé vive en una aldea pequeña en un valle verde, con su esposa, sus tres hijos (Sem, Cam y Jafet) y
las esposas de ellos (Génesis 6:10, 7:13). Dios le pide construir el arca (Génesis 6:14). La aldea es
el hogar: tranquila, cálida, con vida. El arca se levanta en un prado sobre una loma, fuera de la
aldea pero a la vista desde la plaza, así que cada etapa construida se nota desde casa.

Tono: tarde soleada y suave, como Animal Crossing o Tiny Glade. Nada chillón: colores pastel y
cálidos, sombras suaves, poco contraste entre zonas y mucho detalle pequeño.

## 2. Mapa y zonas

**Trazado (22-oct-2026): la aldea crece a lo largo de su calle.** Un trazado radial (plaza
circular con caminos en estrella y casas equidistantes mirando al centro) se ve hecho a compás. Ahora
hay una calle principal que viene del valle, cruza la aldea con curvas y sube a la colina del arca.
La plaza es el ensanche irregular donde se cruza con el camino del río. Las casas se agrupan con la
fachada hacia su calle, y algunos patios comparten murete. Los caminos tienen jerarquía: calle ancha,
callejones que se unen en Y y sendas que se pierden en el pasto. El ancho varía y las orillas tienen
pasto pisado y piedritas.

**Zonas: según el boceto `referencias/villa_noe_boceto.jpg`.** El arca
está en lo alto de una colina al norte (10 m), con un sendero en curvas. El río va por el oeste, con un
puente de piedra y madera. En el centro hay una plaza-mercado con toldos, fogata, pozo y mesas, y las
casas la rodean (la mayoría al este). Los huertos quedan al oeste, hay tres corrales (oeste, sur y
este), un bosque denso al este y el camino al valle sale por el sur entre las colinas. Las casas
siguen siendo de adobe, por fidelidad a la historia. La tabla de abajo es la propuesta inicial y
sirve como referencia de funciones; las posiciones reales están en `data/aldea.json`.

El valle está cerrado por colinas suaves, sin mar: un borde natural en lugar de agua por todos lados.
Mide unos 110 × 90 m, más compacto que la isla actual, para que todo quede a pocos pasos.

| Zona | Dónde | Qué hay | Para qué sirve |
|---|---|---|---|
| Plaza | Centro | Pozo, olivo grande, bancos, cántaros | Punto de referencia y encuentro |
| Casa de Noé | Norte de la plaza | Casa más grande con patio, horno de pan (tannur), telar, huerto | Inicio del capítulo; está la esposa |
| Casas de los hijos | Alrededor de la plaza | 3 casas pequeñas con patio | Sem, Cam, Jafet y sus esposas |
| Vecinos | Sur y este | 3 o 4 casas, puesto de cerámica | Gente que comenta (y duda) del arca |
| Río | Oeste | Arroyo con puente de madera, juncos, piedras | Fibra (juncos) |
| Bosque | Suroeste | Cipreses y árboles redondos agrupados | Madera de gofer (talar) |
| Cantera | Noroeste, al pie de la colina | Rocas grandes lilas | Piedra (picar) |
| Campos y corral | Este | Franjas de trigo y cebada, cerca baja, ovejas y cabras | Ambiente; luego, animales |
| Prado del arca | Loma al este | Claro plano, andamios, pilas de madera, pozos de brea al borde | Construcción del arca |

Los caminos salen de cómo se usa el espacio: de cada puerta a la plaza, y de la plaza a cada zona de
trabajo (río, bosque, cantera, arca). Nada de caminos de relleno.

## 3. Reglas para que no se vea al azar

- **Colocación a mano:** casas, árboles importantes, cercas y caminos tienen posición fija en un
  archivo de datos (`data/aldea.json`). El azar solo sirve para variar un poco la rotación, el tamaño
  y el tono de las piezas pequeñas.
- **Grupos, no lluvia:** el pasto alto, las flores y los arbustos aparecen en grupos de 3 a 9 donde
  tienen sentido: al pie de los muros, junto a las cercas, en las orillas de los caminos, bajo los
  árboles, en la orilla del río y en macetas y huertos. Al centro de los prados, pasto corto y casi
  nada más.
- **Prohibido:** pasto encima de caminos, plazas, patios y suelo de casas, y flores en el bosque
  cerrado.
- **Terreno:** casi plano en la aldea. Una loma suave lleva al arca, y las colinas del borde cierran
  el valle. Los escalones de tierra solo se usan a propósito: un muro de contención junto al río y
  bancales en el huerto. No más curvas de nivel al azar.
- **Densidad:** más detalle cerca de la plaza y de las casas; el bosque, denso pero en manchas; los
  prados, despejados para que se lean los caminos.

## 4. Paleta (menos saturada)

| Uso | Color | | Uso | Color |
|---|---|---|---|---|
| Pasto | `#9cc27a` | | Muros de adobe | `#e8cfa6` |
| Pasto en sombra | `#7fae64` | | Adobe en sombra | `#cfae84` |
| Camino de tierra | `#d8b98c` | | Madera | `#a87b55` |
| Plaza (tierra batida) | `#e6d3ad` | | Tela, toldos | `#e7a48f` / `#9fb7c9` |
| Hojas | `#7fa35c` / `#6f9a52` | | Rocas | `#b3abc0` |
| Agua | `#9fc7d6` | | Cielo | `#a9d3ec` → `#f4e9d8` |

La luz es cálida y suave: sol bajo y dorado, sombras con un poco de azul y saturación normal (sin el
×1,3 actual). El efecto diorama se queda solo como viñeta suave.

## 5. Proporciones

Noé mide 1,55 m (chibi, cabeza grande). Todo se mide contra él:

| Pieza | Medida | | Pieza | Medida |
|---|---|---|---|---|
| Puerta | 1,9 × 1,1 m | | Pozo | Ø 1,4 m, brocal de 0,7 m |
| Muro de casa | 2,4 m de alto | | Olivo de la plaza | 4,5 m |
| Casa pequeña | 5 × 4 m | | Árboles del bosque | 3,5 a 5 m |
| Casa de Noé | 8 × 6 m con patio | | Cerca | 0,8 m |
| Horno (tannur) | Ø 0,8 m, 0,9 m de alto | | Oveja | 0,7 m de alto |
| Camino | 1,6 a 2,2 m de ancho | | Mata de pasto alto | 0,3 a 0,5 m |

Las personas tienen las mismas proporciones chibi que Noé: altura de 1,3 a 1,6 m, y los hijos y
nueras algo más bajos.

## 6. Personajes

- **La esposa de Noé:** sin nombre, como en la Biblia.
- **Sem, Cam y Jafet, y sus esposas.**
- **3 o 4 vecinos** con un par de frases cada uno.
- **Cómo hacerlos:** con la misma cadena que Noé (hoja de giro → Rodin → pulido → rig con
  `rig_noe.py`, que ya sirve para cualquier personaje con la misma postura). Cada uno lleva su
  trabajo, así que conviene empezar por la esposa y los hijos, y dejar a los vecinos para después.

## 7. Recursos: qué se genera, qué se modela y qué se reutiliza

| Pieza | Cómo | Por qué |
|---|---|---|
| Casas de adobe (3 variantes + casa de Noé) | Script de Blender, como `arca.py` | Formas sencillas (cajas redondeadas, techo plano, escalera); así controlamos las medidas exactas |
| Pozo, horno, bancos, cercas, cántaros, cestas | Script de Blender o código | Piezas pequeñas y repetidas; mismo estilo |
| Olivo de la plaza, telar, puesto de cerámica, ovejas y cabras | Generador 3D (Rodin) | Formas orgánicas; quedan mejor generadas |
| Plantas, rocas y pasto | `stylized.gd` (ya existe) | Se reajusta la paleta y se agregan cipreses y olivos |
| Personajes | Rodin + `rig_noe.py` | Mismo estilo que Noé |

Packs CC0 revisados: [KayKit Medieval Hexagon](https://kaylousberg.itch.io/kaykit-medieval-hexagon),
[Kenney Fantasy Town Kit](https://opengameart.org/content/fantasy-town-kit) y
[Quaternius Medieval Village](https://opengameart.org/content/lowpoly-medieval-village-pack). Son
europeos (techos de teja, entramado de madera) y no encajan con una aldea de Mesopotamia. Solo
sirven de inspiración para el nivel de detalle.

Referencias históricas: casas de adobe de una o dos piezas con techo plano (se usaba para dormir y
trabajar), patio con horno de pan y animales cerca de la casa
([historyonthenet](https://www.historyonthenet.com/daily-life-in-the-mesopotamian-countryside),
[TheCollector](https://www.thecollector.com/daily-life-ancient-mesopotamia/)).

## 8. Recorrido del capítulo

1. Noé despierta en su casa. Su esposa le habla en el patio (tutorial de moverse e interactuar).
2. Momento de Génesis 6:13-14: la instrucción del arca.
3. Los hijos ayudan: Sem en el bosque, Cam en la cantera, Jafet en el río. Cada uno explica un
   recurso.
4. Se fabrica en el patio de Noé y se construye en el prado, en 5 etapas. Los vecinos comentan en
   la plaza.
5. Final: llegan los animales de dos en dos (siguiente fase).

## 9. Orden de trabajo

1. Terreno nuevo del valle (plano, loma, río, colinas), caminos y zonas desde `data/aldea.json`,
   paleta y luz nuevas.
2. Casas y piezas de la aldea (script de Blender), colocadas a mano.
3. Vegetación por grupos con las reglas de la sección 3.
4. Personajes: esposa e hijos.
5. Diálogos y recorrido del capítulo.
6. Vecinos, ovejas y detalles.

Cada paso se revisa con capturas contra las referencias antes de seguir.
