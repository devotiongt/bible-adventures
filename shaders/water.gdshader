// Mar: olas suaves, color según profundidad, espuma en la orilla y brillos.
shader_type spatial;
render_mode blend_mix, cull_back, depth_draw_opaque, specular_schlick_ggx;

uniform vec3 deep_color : source_color = vec3(0.05, 0.3, 0.5);
uniform vec3 shallow_color : source_color = vec3(0.3, 0.78, 0.78);
uniform vec3 foam_color : source_color = vec3(0.97, 0.98, 1.0);
uniform float depth_fade = 3.0;
uniform float foam_width = 0.55;
uniform sampler2D depth_tex : hint_depth_texture, filter_linear_mipmap;

varying vec3 world_pos;

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

float waves(vec2 p, float t) {
	return sin(p.x * 0.25 + t * 1.1) * 0.06 + cos(p.y * 0.3 + t * 0.9) * 0.06
			+ sin((p.x + p.y) * 0.6 + t * 1.7) * 0.025;
}

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	VERTEX.y += waves(world_pos.xz, TIME);
}

void fragment() {
	// Profundidad del agua: distancia entre la superficie y lo que hay debajo.
	float raw = texture(depth_tex, SCREEN_UV).r;
	vec4 view = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, raw, 1.0);
	view.xyz /= view.w;
	float water_depth = max(VERTEX.z - view.z, 0.0);

	float d = clamp(water_depth / depth_fade, 0.0, 1.0);
	vec3 color = mix(shallow_color, deep_color, d);

	float n = noise(world_pos.xz * 1.3 + vec2(TIME * 0.4, TIME * 0.3));
	float edge = 1.0 - smoothstep(0.0, foam_width, water_depth);
	float pulse = 0.5 + 0.5 * sin(TIME * 1.6 - water_depth * 8.0);
	float foam = step(0.55, edge * (0.55 + 0.5 * n)) + step(0.92, edge * pulse) * 0.6;
	foam = clamp(foam, 0.0, 1.0);

	// Brillos que se mueven en la superficie.
	vec2 p = world_pos.xz * 0.8;
	float nx = noise(p + vec2(TIME * 0.5, 0.0)) - noise(p + vec2(0.0, TIME * 0.45));
	float nz = noise(p * 1.3 - vec2(TIME * 0.3)) - noise(p * 1.1 + vec2(TIME * 0.35));
	NORMAL = normalize(NORMAL + (VIEW_MATRIX * vec4(nx, 0.0, nz, 0.0)).xyz * 0.25);

	ALBEDO = mix(color, foam_color, foam);
	ALPHA = mix(mix(0.55, 0.9, d), 1.0, foam);
	ROUGHNESS = mix(0.05, 0.6, foam);
	SPECULAR = 0.6;
}
