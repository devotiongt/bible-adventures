// AI-generated village objects (color painted on the vertices). On the wooden parts
// (orange-brown tones) it puts a shared wood brown and a drawn, toy-like grain: soft wavy
// stripes along the piece, the odd knot and a faint shine on the edges.
shader_type spatial;

// Objects painted with a material map (tools/blender/paint_materials.py) come with a texture
// with the color and, in the alpha, the wood mark; the rest, the color on the vertices.
uniform bool use_texture = false;
// Pieces made by script: a fixed color per material (no vertex colors).
uniform bool use_flat_color = false;
uniform vec4 flat_color : source_color = vec4(1.0);
uniform sampler2D albedo_tex : source_color, filter_linear;   // No mipmaps: doesn't blend neighboring pieces.
uniform float wood = 1.0;          // 0: no grain (clay, cloth, stone); 1: grain where the color is wood.
// Wood brown (from references/village_objects.jpg). From the model only how much lighter or
// darker each patch is gets kept, so all the wood in the village shares the same tone.
uniform vec3 wood_color : source_color = vec3(0.60, 0.37, 0.22);
uniform float grain_scale = 5.0;   // Stripes per meter, across the piece.
// Striped awnings: faces marked with alpha 0 are cloth; their color alternates with cream.
// Alpha 0.7: stall goods (clay, cloth, fruit), no wood grain.
uniform vec3 stripe_cream : source_color = vec3(0.96, 0.92, 0.84);
uniform float stripe_width = 0.34;

varying vec3 local_pos;
varying vec3 local_normal;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
			mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

vec3 rgb2hsv(vec3 c) {
	vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
	vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
	vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
	float d = q.x - min(q.w, q.y);
	return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + 1e-10)), d / (q.x + 1e-10), q.x);
}

void vertex() {
	local_pos = VERTEX;
	local_normal = abs(NORMAL);
}

void fragment() {
	vec4 src = use_texture ? texture(albedo_tex, UV) : (use_flat_color ? flat_color : COLOR);
	vec3 base = src.rgb;
	// Is it wood? Hue between reddish and yellowish, fairly saturated and not too light (in linear space).
	vec3 hsv = rgb2hsv(pow(base, vec3(1.0 / 2.2)));
	float is_wood = smoothstep(0.01, 0.04, hsv.x) * (1.0 - smoothstep(0.11, 0.14, hsv.x))
			* smoothstep(0.3, 0.45, hsv.y) * (1.0 - smoothstep(0.88, 0.95, hsv.z)) * wood;
	// Face coordinates: "x" runs along the grain, "y" across it.
	vec2 uv;
	if (local_normal.y > 0.6) {
		uv = local_pos.xz;
	} else if (local_normal.x > 0.6) {
		uv = local_pos.yz;
	} else {
		uv = local_pos.xy;
	}
	float wave = noise(vec2(uv.x * 1.3, uv.y * 3.0)) * 1.4;
	float bands = sin((uv.y * grain_scale + wave) * 6.2832);
	float streak = smoothstep(0.35, 0.95, bands);                   // Soft light stripes.
	float dark = smoothstep(-0.55, -0.95, bands) * 0.6;             // Thin dark lines.
	float knot_cell = hash(floor(uv * vec2(1.5, 4.0)));
	vec2 knot_pos = fract(uv * vec2(1.5, 4.0)) - 0.5;
	float knot = step(0.86, knot_cell) * smoothstep(0.16, 0.08, length(knot_pos * vec2(1.0, 0.6)));
	vec3 wood_col = wood_color * mix(0.8, 1.15, smoothstep(0.45, 0.9, hsv.z));
	wood_col *= 1.0 + streak * 0.16 - dark * 0.38 - knot * 0.32;
	// Vertex alpha: 0 striped cloth, 0.7 goods (no grain), 1 everything else.
	float cloth = 1.0 - step(0.35, src.a);
	is_wood *= step(0.85, src.a);
	float stripe = step(0.5, fract(local_pos.x / (stripe_width * 2.0) + 0.25));
	vec3 cloth_col = mix(stripe_cream, base, stripe);
	ALBEDO = mix(mix(base, wood_col, is_wood), cloth_col, cloth);
	ROUGHNESS = mix(0.85, 0.7, is_wood);
	SPECULAR = mix(0.2, 0.35, is_wood);
	// Soft shine on the wood edges (toy-like "varnished" edges).
	RIM = 0.25 * is_wood;
	RIM_TINT = 0.6;
}
