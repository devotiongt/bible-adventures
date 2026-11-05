// Procedural wood for the ark: planks with seams, grain and tone variation.
shader_type spatial;

uniform vec3 base_color : source_color = vec3(0.64, 0.44, 0.28);
uniform float plank_width = 0.32;
uniform float plank_length = 2.6;
// Draws plank seams. Turn off on models that already have real planks.
uniform bool seams = true;

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

void vertex() {
	local_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	local_normal = abs((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec2 uv;
	if (local_normal.y > 0.6) {
		uv = local_pos.xz;
	} else if (local_normal.x > 0.6) {
		uv = local_pos.zy;
	} else {
		uv = local_pos.xy;
	}
	float row = floor(uv.y / plank_width);
	float row_rand = hash(vec2(row, 7.3));
	float across = fract(uv.y / plank_width);
	float seam = smoothstep(0.0, 0.06, across) * smoothstep(1.0, 0.94, across);
	float along = uv.x / plank_length + row_rand * 5.0;
	float joint = smoothstep(0.0, 0.012, fract(along)) * smoothstep(1.0, 0.988, fract(along));
	float plank_id = hash(vec2(row, floor(along)));

	float grain = noise(vec2(uv.x * 2.0, uv.y * 45.0)) * 0.6 + noise(vec2(uv.x * 0.4, uv.y * 9.0)) * 0.4;
	vec3 color;
	if (seams) {
		color = base_color * (0.82 + plank_id * 0.3) * (0.82 + grain * 0.32);
		color *= mix(0.45, 1.0, seam * joint);
	} else {
		// The per-plank variation comes in the model's vertex color.
		color = base_color * COLOR.rgb * (0.85 + grain * 0.3);
	}

	ALBEDO = color;
	ROUGHNESS = 0.82;
	SPECULAR = 0.25;
}
