// Hojas, hierba y flores: textura con recorte alfa, viento y luz que atraviesa las hojas.
shader_type spatial;
render_mode cull_disabled, depth_draw_opaque;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 albedo : source_color = vec4(1.0);
uniform float alpha_cut = 0.35;
uniform float wind_strength = 0.06;
uniform float wind_speed = 1.3;
uniform float sway_height = 4.0; // Altura local a la que el balanceo es completo.
uniform float tint_variation = 0.12;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void vertex() {
	vec3 world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float h = clamp(VERTEX.y / sway_height, 0.0, 1.0);
	float t = TIME * wind_speed + world.x * 0.12 + world.z * 0.09;
	vec3 sway = vec3(sin(t), 0.0, cos(t * 0.83)) * h * h;
	vec3 flutter = vec3(sin(t * 3.7 + VERTEX.x * 3.0), 0.0, cos(t * 3.3 + VERTEX.z * 3.0)) * 0.3 * h;
	VERTEX += (sway + flutter) * wind_strength;
}

void fragment() {
	vec4 tex = texture(albedo_tex, UV) * albedo;
	float v = hash(floor(NODE_POSITION_WORLD.xz * 3.0));
	ALBEDO = tex.rgb * (1.0 - tint_variation * 0.5 + v * tint_variation);
	ALPHA = tex.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	ROUGHNESS = 0.85;
	SPECULAR = 0.15;
	BACKLIGHT = vec3(0.35, 0.4, 0.2);
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}
}
