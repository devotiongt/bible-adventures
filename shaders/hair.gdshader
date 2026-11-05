// Gray hair and beard: uses the original texture only for the shape and relief.
shader_type spatial;
render_mode cull_disabled, depth_draw_opaque;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap;
uniform vec3 tint : source_color = vec3(0.86, 0.84, 0.8);
uniform float alpha_cut = 0.4;

void fragment() {
	vec4 tex = texture(albedo_tex, UV);
	float lum = dot(tex.rgb, vec3(0.299, 0.587, 0.114));
	ALBEDO = tint * (0.7 + lum * 0.9);
	ALPHA = tex.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	ROUGHNESS = 0.75;
	SPECULAR = 0.3;
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}
}
