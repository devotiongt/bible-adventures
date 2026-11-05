// Toy tongue of fire (scripts/fire.gd): it sways, stretches and shrinks, and goes from yellow at the base
// to orange at the tip, with an almost white core at the bottom. No lighting of its own: the color is already the fire's.
shader_type spatial;
render_mode unshaded, cull_disabled;

uniform vec3 base_color : source_color = vec3(1.0, 0.86, 0.38);
uniform vec3 tip_color : source_color = vec3(0.98, 0.45, 0.14);
uniform vec3 core_color : source_color = vec3(1.0, 0.97, 0.78);
uniform float height = 0.4;        // Height of the mesh, to know how high each vertex is.
uniform float speed = 1.0;
instance uniform float phase = 0.0;

varying float t;

void vertex() {
	t = clamp(VERTEX.y / height, 0.0, 1.0);
	float time = TIME * speed + phase;
	// Pulses in height (fast and irregular) and sways sideways, more the higher up.
	float pulse = 1.0 + 0.07 * sin(time * 7.0) + 0.04 * sin(time * 11.3 + 1.7);
	VERTEX.y *= pulse;
	VERTEX.xz *= 1.0 - 0.04 * sin(time * 7.0);
	float sway = t * t;
	VERTEX.x += sway * height * (0.16 * sin(time * 3.1) + 0.06 * sin(time * 8.7));
	VERTEX.z += sway * height * 0.1 * sin(time * 2.3 + 0.8);
}

void fragment() {
	vec3 color = mix(base_color, tip_color, smoothstep(0.15, 0.85, t));
	// Bright core: the part facing the camera, in the bottom half.
	float facing = abs(dot(NORMAL, VIEW));
	float core = smoothstep(0.6, 0.92, facing) * (1.0 - smoothstep(0.25, 0.6, t));
	ALBEDO = mix(color, core_color, core);
}
