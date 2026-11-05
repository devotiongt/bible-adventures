// Terrain: grass and sand per vertex, and on top dirt with crisp edges (path, yards, the ark
// clearing and banks) and the plaza paving. Each vertex carries how much of each thing it is (UV, UV2);
// cutting that value at 0.5 per pixel makes the edges follow smooth curves instead of the triangle
// grid. In the plaza the paths end: it's a single flagstone floor with its curb.
shader_type spatial;
render_mode cull_back;

uniform vec3 cliff_color : source_color = vec3(0.71, 0.45, 0.24);
uniform vec3 cliff_dark : source_color = vec3(0.56, 0.35, 0.18);
uniform vec3 path_color : source_color = vec3(0.66, 0.41, 0.18);
uniform vec3 dirt_color : source_color = vec3(0.69, 0.48, 0.26);
uniform vec3 stone_light : source_color = vec3(0.80, 0.79, 0.76);
uniform vec3 stone_dark : source_color = vec3(0.66, 0.65, 0.63);
uniform vec3 mortar_color : source_color = vec3(0.55, 0.60, 0.40);
uniform vec3 curb_color : source_color = vec3(0.58, 0.57, 0.55);
uniform float stone_size = 0.85;

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float edge(float v) {
	float w = max(fwidth(v), 0.001);
	return smoothstep(0.5 - w, 0.5 + w, v);
}

vec2 hash2(vec2 p) {
	p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
	return fract(sin(p) * 43758.5453);
}

// Irregular flagstones (Voronoi): distance to the stone's edge and a value unique to each one.
vec2 flagstones(vec2 p) {
	vec2 cell = floor(p);
	vec2 f = fract(p);
	float d1 = 8.0;
	float d2 = 8.0;
	vec2 id = vec2(0.0);
	for (int j = -1; j <= 1; j++) {
		for (int i = -1; i <= 1; i++) {
			vec2 g = vec2(float(i), float(j));
			vec2 o = 0.15 + 0.7 * hash2(cell + g);
			float d = length(g + o - f);
			if (d < d1) {
				d2 = d1;
				d1 = d;
				id = cell + g;
			} else if (d < d2) {
				d2 = d;
			}
		}
	}
	return vec2(d2 - d1, hash2(id).x);
}

void fragment() {
	float fleck = COLOR.a - 0.5;   // Tone shift of the triangle (the little "triangles" of the grass).
	float plaza = UV2.y;
	vec3 c = COLOR.rgb;
	vec3 strata = mix(cliff_color, cliff_dark, clamp(0.5 + 0.35 * sin(world_pos.y * 14.0), 0.0, 1.0));
	c = mix(c, strata * (1.0 + fleck), edge(UV.x));
	float in_plaza = edge(plaza);
	c = mix(c, dirt_color * (1.0 + fleck), edge(UV2.x) * (1.0 - in_plaza));
	c = mix(c, path_color * (1.0 + fleck), edge(UV.y) * (1.0 - in_plaza));
	// Paving: flagstones of slightly different tones, dirt joints and a slight darkening at the edges of
	// each stone; around it, a curb of darker stone.
	vec2 st = flagstones(world_pos.xz / stone_size);
	float joint = smoothstep(0.03, 0.09, st.x);
	vec3 stone = mix(stone_dark, stone_light, st.y) * mix(0.9, 1.0, smoothstep(0.05, 0.3, st.x));
	vec3 paving = mix(mortar_color, stone, joint);
	float curb = 1.0 - edge(plaza - 0.12);
	paving = mix(paving, curb_color * mix(0.92, 1.0, st.y), curb);
	c = mix(c, paving, in_plaza);
	ALBEDO = c;
	ROUGHNESS = mix(1.0, 0.85, in_plaza);
	SPECULAR = mix(0.0, 0.15, in_plaza);
}
