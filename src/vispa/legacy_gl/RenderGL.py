"""Active legacy OpenGL mesh and SWC renderer.

Version: 1.11.0.dev4 (local/unreleased)
Last updated: 2026-10-22
Change history: ../../../CHANGELOG.md
Status: candidate

The renderer requires an explicit local root mesh; neuron geometry is added from
an explicitly selected local processed SWC via GeometryAdapter.readFile.
"""

from . import glutils, Node, Arcball, GeometryAdapter
import glm
import math
import os
import OpenGL
from OpenGL.GL import *
from OpenGL.GL.shaders import *
import numpy as np
import glfw,glm
import trimesh
from PIL import Image
from pathlib import Path


neuronVertShader = """
# version 430 core
uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;
layout (location = 0) in vec3 position;
layout (location = 1) in vec3 vertexcolor;
layout (location = 2) in vec3 normal;
layout (location = 3) in float type;
uniform vec3 color;
uniform int isVertexcolor;
out vec4 fColor;
out VS_OUT {
    vec4 color;
    vec4 camera;
    vec3 predir;
    mat4 model;
    mat4 projection;
    mat4 view;

} vs_out;
out vec4 position2;
	out vec3 light;
vec4 colors[]=vec4[10](vec4(1,0,0,0), vec4(1,0.67,0,0), vec4(0.75,0.24,1,0),vec4(0,0,1,0),vec4(0,1,0,0),vec4(0,0.67,0,0),vec4(0,0.67,1,0),vec4(0.67,1,0,0),vec4(0.67,0,1,0),vec4(1,0.33,1,0));

void main (void) {
	if (isVertexcolor>0)
		vs_out.color  =vec4(vertexcolor,0.5);
	else{
		vs_out.color  =vec4(color,1.0);
		}
	if (type>=13)
		vs_out.color  =colors[int(type-13)];
	fColor=vs_out.color;
	vs_out.model = model;
	vs_out.projection = projection;
	vs_out.view = view;


	vs_out.predir = normalize(normal);
	position2 = vec4(position,1.0);
	light = normalize(inverse(view*model)*vec4(0.0, 0.0, 1.0, 0.0)).xyz;

	vec4 pos  = projection*view * model * vec4(position,1.0);
	gl_Position=pos;//vec4(position,1.0);
}
"""
neuronGeomShader="""
#version 330 core
layout (lines) in;
layout (triangle_strip,max_vertices=4) out;
in VS_OUT {
    vec4 color;
    vec4 camera;
    vec3 predir;
    mat4 model;
    mat4 projection;
    mat4 view;
} gs_in[]; 

out vec4 fColor;
void main(){
	float width=20;
	mat4 model = gs_in[0].model;
	mat4 view = gs_in[0].view;
	mat4 projection = gs_in[0].projection;
    vec4 pos_in_camera0 = view*model * gl_in[0].gl_Position;
	vec4 camera0 = vec4(normalize(pos_in_camera0.xyz),1.0);
	vec4 pos_in_camera1 = view*model * gl_in[1].gl_Position;
	vec4 camera1 = vec4(normalize(pos_in_camera1.xyz),1.0);
	mat4 mvp = projection*view*model;
	
	vec4 norm =normalize(vec4(cross(camera0.xyz,(view*model*vec4(gs_in[0].predir,1)).xyz),0));
	gl_Position = projection*( view*model*gl_in[0].gl_Position+norm*width);
	fColor = gs_in[0].color;
	EmitVertex();

	vec4 dir= view*model*vec4(normalize((gl_in[0].gl_Position-gl_in[1].gl_Position).xyz),1.0);
	vec4 norm0 = normalize(vec4(cross(camera1.xyz,dir.xyz),0));
	gl_Position = projection*( view*model*gl_in[1].gl_Position+norm0*width);
	fColor = gs_in[1].color;
	EmitVertex();
	
	gl_Position = mvp*gl_in[0].gl_Position;
	fColor = gs_in[0].color;
	EmitVertex();
	gl_Position =  mvp*gl_in[1].gl_Position;
	fColor = gs_in[1].color;
	EmitVertex();
	//gl_Position = gs_in[0].projection*(gl_in[0].gl_Position-vec4(cross(gs_in[1].camera.xyz,dir.xyz),1)*width);
	//fColor = gs_in[0].color;
	//EmitVertex();
	//gl_Position = gs_in[1].projection*(gl_in[1].gl_Position-vec4(cross(gs_in[1].camera.xyz,dir.xyz),1)*width);
	//fColor = gs_in[1].color;
	//EmitVertex();


	EndPrimitive();
}



"""
neuronFragShader = """
#version 430 core
in vec4 position2;
in vec3 light;

in vec4 fColor;
out vec4 color;
void main()
{
		vec3 norm = normalize(cross(dFdx(position2.xyz), dFdy(position2.xyz)));
		float diffuse = max((dot((light), (norm.xyz))), 0.0);
	color = vec4(fColor.xyz*(0.7+0.3*diffuse),1.0);

}	
"""
neuronFragShaderLine = """
#version 430 core
in vec4 position2;
in vec3 light;

in vec4 fColor;
out vec4 color;
void main()
{
		vec3 norm = normalize(cross(dFdx(position2.xyz), dFdy(position2.xyz)));
		float diffuse = max((dot((light), (norm.xyz))), 0.0);
	color = vec4(fColor.xyz,1.0);
}	
"""
vertShader="""
			#version 330 core

			layout (location = 0) in vec3 position;
			layout (location = 1) in vec3 normal;
			uniform mat4 model;
			uniform mat4 view;
			uniform mat4 projection;
			uniform vec3 color;
			uniform vec4 clip_plane = vec4(0.0, 0.0, 1.0, -5700.0);
			out vec4 v_color;
			out vec3 tnorm;
			out vec3 view_direction;
			void main()
			{
				gl_ClipDistance[0] = dot(vec4(position,1.0), clip_plane);
				vec4 pos_in_camera = view*model * vec4(position, 1.0);

				v_color =vec4(color,0.5);
				gl_Position =projection*pos_in_camera;
				tnorm = normalize((view*model*vec4(normal.xyz, 0.0)).xyz);
				view_direction = normalize(pos_in_camera.xyz);

			}
			"""
fragShader="""
			#version 330 core
			in vec4 v_color;
			in vec3 tnorm;
			in vec3 view_direction;
			void main()
			{
				float edginess = 1.0 - abs(dot(tnorm, view_direction));
				float opacity = clamp(edginess - 0.30, 0.0, 0.5);
				// Darken compartment at the very edge\n          
				float blackness = pow(edginess, 4.0) - 0.3;
				vec3 c = mix(v_color.xyz*0.8, vec3(0, 0, 0), blackness);
				gl_FragColor = vec4(c, opacity);
			//	gl_FragColor = v_color;
			}
			"""
vertShader1 = """
						#version 430 core\n
						layout(location = 0) in vec3 position;
					layout(location = 1) in vec3 normal;
					layout (location = 2) in vec3 vertexcolor;
					layout (location = 3) in vec2 texcoord;

					uniform mat4 model;
					uniform mat4 view;
					uniform mat4 projection;
					uniform vec3 color;
					uniform vec4 clip_plane ;
					uniform int isVertexcolor;

					out vec3 tnorm;
					out vec3 light;
					out vec3 view_direction;
					out vec3 vertcolor;
					out vec2 v_texture;
					out float depth;
					void main(void) {
						gl_ClipDistance[0] = dot(vec4(position,1.0), clip_plane);
						light = normalize( vec4(0.0, 0.0, 1.0,1.0)).xyz;
						vec4 pos_in_camera = view*model * vec4(position.xyz, 1.0);
						gl_Position = projection* pos_in_camera;
						tnorm = normalize((view*model*vec4(normal.xyz, 0.0)).xyz);
						//tnorm = vNormal.xyz;
						view_direction = normalize(pos_in_camera.xyz);
						vertcolor = color;
						if (isVertexcolor>0)
							vertcolor =vertexcolor;
						else
							vertcolor = color;
						v_texture = texcoord;
					}
					"""
fragShaderMap = """
						#version 430 core\n
						in vec3 tnorm;
					in vec3 vertcolor;
					in vec3 light;
					in vec3 view_direction;
					in vec2 v_texture;
					out vec4 fColor;
					uniform sampler2D s_texture;

					void main(void) {

						float diffuse = max((dot((light), (tnorm.xyz))), 0.0)*0.6;
						vec4  color = vec4(diffuse, diffuse, diffuse, 0.4) + vec4(vertcolor,0.1)*0.5;
						fColor = texture(s_texture, v_texture) ;
						if(fColor.a<0.1)
							discard;
						//fColor =  vec4(color.xyz, 1.0f);
					}
					"""
fragShaderPoints = """
						#version 430 core\n
						in vec3 tnorm;
					in vec3 vertcolor;
					in vec3 light;
					in vec3 view_direction;
					in vec2 v_texture;
					out vec4 fColor;
					uniform sampler2D s_texture;

					void main(void) {
						vec4  color = vec4(vertcolor, 1.0);
						fColor=color;
					}
					"""
fragShader1 = """
						#version 430 core\n
						in vec3 tnorm;
					in vec3 vertcolor;
					in vec3 light;
					in vec3 view_direction;
					in vec2 v_texture;
					out vec4 fColor;
					uniform sampler2D s_texture;

					void main(void) {

						float diffuse = max((dot((light), (tnorm.xyz))), 0.0)*0.6;
						fColor = vec4(diffuse, diffuse, diffuse, 0.4) + vec4(vertcolor,0.1)*0.5;
						
					}
					"""
class GeometryGLHandle:
	def __init__(self):
		self.submit=False
		self.program=None
		self.RenderModel=-1
		pass
	def setGeometry(self,geometry):
		self.Geometry = geometry
		pass
	def Submit(self):
		if not self.submit:
			## do submit
			if self.Geometry.drawModel=='triangles' and self.Geometry.type==-1:
				if self.RenderModel==0:
					self.program = glutils.loadShaders(vertShader, fragShader)
				else:
					self.program = glutils.loadShaders(vertShader1, fragShader1)
			elif self.Geometry.drawModel=='normal':
				self.program = glutils.loadShaders(vertShader1, fragShaderMap)
			elif self.Geometry.drawModel=='points':
				self.program = glutils.loadShaders(vertShader1, fragShaderPoints)
			elif self.Geometry.drawModel=='lines' :
				self.program = glutils.loadShaders(neuronVertShader, neuronFragShaderLine)
			else:
				self.program = glutils.loadShaders(neuronVertShader, neuronFragShader)

			# self.program = glutils.loadShaders(strVS, strFS)
			glUseProgram(self.program)
				
			# set up vertex array object (VAO)
			self.vao = glGenVertexArrays(1)
			glBindVertexArray(self.vao)
			self.ebo=glGenBuffers(1);
			# set up VBOs
			vertexData = np.array(self.Geometry.vertex, np.float32).reshape(-1)
			self.vertexBuffer = glGenBuffers(5)
			glBindBuffer(GL_ARRAY_BUFFER, self.vertexBuffer[0])
			glBufferData(GL_ARRAY_BUFFER, 4*vertexData.size, vertexData, 
						GL_STATIC_DRAW)
			loc = glGetAttribLocation(self.program, b"position")
			if loc>=0:
				glEnableVertexAttribArray(loc)
				glVertexAttribPointer(loc, 3, GL_FLOAT, GL_FALSE, 0, None)

			normalData = np.array(self.Geometry.normal, np.float32)
			glBindBuffer(GL_ARRAY_BUFFER, self.vertexBuffer[1])
			glBufferData(GL_ARRAY_BUFFER, 4*(normalData.size), normalData, 
						GL_STATIC_DRAW)

			loc = glGetAttribLocation(self.program, b"normal")
			if loc>=0:
				glEnableVertexAttribArray(loc)
				glVertexAttribPointer(loc, 3, GL_FLOAT, GL_FALSE, 0, None)

			if len(self.Geometry.color)==len(self.Geometry.vertex):
				colorData = np.array(self.Geometry.color, np.float32)
				glBindBuffer(GL_ARRAY_BUFFER, self.vertexBuffer[2])
				glBufferData(GL_ARRAY_BUFFER, 4*colorData.size, colorData, 
						GL_STATIC_DRAW)
				loc = glGetAttribLocation(self.program, b"vertexcolor")
				if loc>=0:
					glEnableVertexAttribArray(loc)
					glVertexAttribPointer(loc, 3, GL_FLOAT, GL_FALSE, 0, None)
				glUniform1i(glGetUniformLocation(self.program, "isVertexcolor"), 1)
			else:
				glUniform1i(glGetUniformLocation(self.program, "isVertexcolor"), 0)
			glUniform3fv(glGetUniformLocation(self.program, "color"),1, self.Geometry.uniformColor)

			#texture
			if len(self.Geometry.texcoord)==len(self.Geometry.vertex):
				texcoordData = np.array(self.Geometry.texcoord, np.float32)
				glBindBuffer(GL_ARRAY_BUFFER, self.vertexBuffer[3])
				glBufferData(GL_ARRAY_BUFFER, 4*texcoordData.size, texcoordData, 
						GL_STATIC_DRAW)
				loc = glGetAttribLocation(self.program, b"texcoord")
				if loc>=0:
					glEnableVertexAttribArray(loc)
					glVertexAttribPointer(loc, 2, GL_FLOAT, GL_FALSE, 0, None)
				# glUniform1i(glGetUniformLocation(self.program, "isVertexcolor"), 1)
			else:
				# glUniform1i(glGetUniformLocation(self.program, "isVertexcolor"), 0)
				pass
			if len(self.Geometry.types)==len(self.Geometry.vertex):

				typeData = np.array(self.Geometry.types, np.uint32)
				glBindBuffer(GL_ARRAY_BUFFER, self.vertexBuffer[4])
				glBufferData(GL_ARRAY_BUFFER, 4*(typeData.size), typeData, 
							GL_STATIC_DRAW)
				loc = glGetAttribLocation(self.program, b"type")
				if loc>=0:
					glEnableVertexAttribArray(loc)
					glVertexAttribPointer(loc, 1, GL_UNSIGNED_INT, GL_FALSE, 0, None)


			self.textureID = 0
			
			if len(self.Geometry.textures):
				texture = glGenTextures(1)
				self.textureID = texture
				glBindTexture(GL_TEXTURE_2D, texture)
				# Set the texture wrapping parameters
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
				# Set texture filtering parameters
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
				glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
				img = self.Geometry.textures[0]['diff']
				glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img.shape[0], img.shape[1], 0, GL_RGBA, GL_UNSIGNED_BYTE, img)
				glGenerateMipmap(GL_TEXTURE_2D);
				
			self.modelloc = glGetUniformLocation(self.program, "model")
			self.viewloc = glGetUniformLocation(self.program, "view")
			self.projectionloc = glGetUniformLocation(self.program, "projection")
			self.clipplaneloc = glGetUniformLocation(self.program, "clip_plane")
			# glBindBuffer(GL_ARRAY_BUFFER, self.vertexBuffer[2])
			# glBufferData(GL_ARRAY_BUFFER, 4*normalData.size, normalData, 
			# 			GL_STATIC_DRAW)
			# loc = glGetAttribLocation(self.program, b"color")
			# if loc>=0:
			# 	glEnableVertexAttribArray(loc)
			# 	glVertexAttribPointer(loc, 3, GL_FLOAT, GL_FALSE, 0, None)

			indexData = np.array(self.Geometry.index, np.uint32)
			glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
			glBufferData(GL_ELEMENT_ARRAY_BUFFER, 4*indexData.size, indexData, GL_STATIC_DRAW)
			# unbind VAO
			glBindVertexArray(0)

			self.submit=True
		

class RenderGL:
	def __init__(self,size=(800, 600),renderModel=0,near=10000,far=None,species='mouse', *, root_mesh_path=None):
		self.near = near
		self.far=far
		self.near=near
		# time.sleep(20)
		self.isLine=True
		self.__createWindow = False
		# self.__createWindow__(size)
		self.RenderModel=renderModel
		self.size=size
		self.pointsize=2
		self.geometries=[]
		self.species=species # retained legacy metadata; it does not select or fetch data
		if root_mesh_path is None:
			raise ValueError("root_mesh_path is required; supply an explicit local mesh file")
		mesh_path = Path(root_mesh_path).expanduser()
		if not mesh_path.is_file():
			raise FileNotFoundError(f"local root mesh does not exist: {mesh_path}")
		rootmesh = self.loadGeometry(os.fspath(mesh_path.resolve()))
		rootmesh.uniformColor = [0.8,0.8,0.8]
		handle = GeometryGLHandle()
		handle.RenderModel = self.RenderModel
		handle.setGeometry(rootmesh)
		self.rootMesh = handle
		self.rootMesh.name='root'
		bounds=self.rootMesh.Geometry.bound
		self.root_bounds = np.asarray(bounds, dtype=float).copy()
		self.gl_version = None
		boundLength=np.linalg.norm(bounds[0]-bounds[1])
		self.far = boundLength*10 if far is None else far
		self.center = glm.vec3(bounds[1,0]+bounds[0,0],bounds[1,1]+bounds[0,1],bounds[1,2]+bounds[0,2])/2.0
		self.originModel = glutils.translate(-self.center[0],-self.center[1],-self.center[2])
		self.model = glutils.translate(-self.center[0],-self.center[1],-self.center[2])
		eye=[-boundLength,-boundLength,boundLength]
		center=[0,0,0]
		up=[0,-1,0]
		self.view=  glutils.lookAt(eye,center,up)
		r=size[0]/ float(size[1])
		self.fov=45
		# self.projection=glm.perspective(self.fov, size[0] / float(size[1]),1, 1500.0)
		self.projection = glutils.perspective(self.fov, size[0] / float(size[1]),self.near, self.far)
		# self.projection = glutils.ortho(-size[0]*r*20, size[0]*r*20, size[0]*20,-size[0]*20, -30000, 30000)
		self.geometries.append(self.rootMesh)
		self.prepos=[0,0]
		self.action=''
		self.rotxangle =0
		self.rotyangle =0
		self.xaxis = glm.vec4(1.0, 0.0, 0.0,1.0)
		self.yaxis = glm.vec4(0.0, 1.0, 0.0,1.0)
		self.backGroundColor = [0.0,0.0,0.0]
		self.clipEnable=False
		self.clipPlane=[0,0,1,-5700]
		self.linewidth=1
		pass
	
	def setPointSize(self,size):
		self.pointsize=size

	def loadGeometry(self,filename):
		mesh = trimesh.load(filename)
		geometry = Node.Geometry();
		geometry.vertex = mesh.vertices
		geometry.index = mesh.faces
		geometry.normal = mesh.vertex_normals
		geometry.bound=mesh.bounds

		return geometry

	def __createWindow__(self,size):
		# Initialize the library
		if self.__createWindow == False:
			if not glfw.init():
				raise RuntimeError("GLFW initialization failed; check the graphics driver and display session")
			self.arcball= Arcball.Arcball( size[0], size[1], 0.1, True, True );
			glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
			glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
			glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
			glfw.window_hint(glfw.SAMPLES,4)
			# Create a windowed mode window and its OpenGL context
			self.window = glfw.create_window(size[0], size[1], "neuronVis", None, None)
			if not self.window:
				glfw.terminate()
				raise RuntimeError("could not create an OpenGL 4.3 core window; verify GPU/driver support")
		
			# Make the window's context current
			glfw.make_context_current(self.window)
			glfw.swap_interval(1)
			version = glGetString(GL_VERSION)
			if not version:
				glfw.destroy_window(self.window)
				glfw.terminate()
				self.window = None
				raise RuntimeError("OpenGL context did not report a version string")
			if isinstance(version, bytes):
				version = version.decode("ascii", errors="replace")
			try:
				actual_version = tuple(int(part) for part in version.split()[0].split(".")[:2])
			except (IndexError, ValueError) as exc:
				glfw.destroy_window(self.window)
				glfw.terminate()
				self.window = None
				raise RuntimeError(f"unrecognized OpenGL version string: {version!r}") from exc
			if actual_version < (4, 3):
				glfw.destroy_window(self.window)
				glfw.terminate()
				self.window = None
				raise RuntimeError(f"OpenGL 4.3 is required by the legacy shaders; found {version}")
		
			self.gl_version = version
			# Install a key handler
			glfw.set_key_callback(self.window, self.on_key)
			glfw.set_window_size_callback(self.window, self.on_resize)
			glfw.set_cursor_pos_callback(self.window,self.on_mouse_callback)
			glfw.set_scroll_callback(self.window,self.on_scroll_callback)
			glfw.set_mouse_button_callback(self.window,self.on_mouse_button_callback)
			self.__createWindow = True
	def __del__(self):
		if getattr(self, "window", None) is not None:
			self.closeWindow()
	def addGeometry(self,geometry,color=[1.0,1.0,1.0],highlight=False):
		handle = GeometryGLHandle()
		if geometry.drawModel=='triangles':
			handle.RenderModel = self.RenderModel
		if geometry.uniformColor is None:
			geometry.uniformColor=color
		handle.setGeometry(geometry)
		self.geometries.append(handle)
		geometry.highLight=highlight
		for geo in geometry.children:
			self.addGeometry(geo,color,highlight)
		pass
	def setLineWidth(self,width):
		self.linewidth=width
		pass
	def addMask(self,mask):
		pass
	def savepng(self,filename):
		self.__createWindow__(self.size)

		width =self.size[0]
		height = self.size[1]
		ratio = width / float(height)
		glViewport(0, 0, width, height)
		glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
		glClearColor(self.backGroundColor[0],self.backGroundColor[1],self.backGroundColor[2],0.0)
		glDisable(GL_DEPTH_TEST)
		glEnable(GL_BLEND)
		glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
		self.render()
		glBindFramebuffer(GL_FRAMEBUFFER,0)
		color=glReadPixels(0,0,self.size[0],self.size[1],GL_RGB,GL_FLOAT)
		np_arr2=color.copy()
		np_arr2 = (np_arr2*255).astype(np.ubyte)
		np_arr2=np_arr2.reshape(self.size[1],self.size[0],3)
		np_arr2=np.flip(np_arr2,axis=0)

		img = Image.fromarray(np_arr2)
		path = Path(filename)
		path = path.parent
		if not path.exists():
			path.mkdir(parents=True, exist_ok=True)
		img.save(filename)
		pass


	def render(self):
		# Render here
		glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
		glClearColor(self.backGroundColor[0],self.backGroundColor[1],self.backGroundColor[2],0.0)

		# tri.render()
		# glLineWidth(self.linewidth)

		# print(len(self.geometries))
		for geo in self.geometries:
			if geo.Geometry.hide:
				continue
			geo.Submit()
			glBindVertexArray(geo.vao)
			glUseProgram(geo.program)  
			if self.clipEnable:
				glEnable(GL_CLIP_DISTANCE0 )
			else:
				glDisable(GL_CLIP_DISTANCE0)
			glActiveTexture(GL_TEXTURE0)  # 在绑定纹理之前先激活纹理单元
			glBindTexture(GL_TEXTURE_2D, geo.textureID)

			# loc = glGetUniformLocation(geo.program, "model")
			glUniformMatrix4fv(geo.modelloc,1, GL_FALSE, self.model)
			glUniformMatrix4fv(geo.viewloc,1, GL_FALSE, self.view)
			glUniformMatrix4fv(geo.projectionloc,1, GL_FALSE, self.projection);
			# glDrawArrays(GL_TRIANGLES, 0, 6)
			# glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, geo.ebo)
			if geo.RenderModel==1 and geo.Geometry.type==-1:
				glEnable(GL_BLEND)
				glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
				glEnable(GL_CULL_FACE)
				glCullFace(GL_BACK)
			elif geo.RenderModel==0 and geo.Geometry.type==-1: 	
				glEnable(GL_BLEND)			
				glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
			else:
				glDisable(GL_BLEND)
			glEnable(GL_DEPTH_TEST)

			if geo.Geometry.drawModel=='triangles' and geo.Geometry.type==-1:
				glDisable(GL_DEPTH_TEST)
			elif geo.Geometry.drawModel=='triangles' and (geo.Geometry.type==0 or geo.Geometry.type==1):
				# glDisable(GL_BLEND)
				glEnable(GL_DEPTH_TEST)
			if geo.Geometry.highLight:
				glDisable(GL_DEPTH_TEST)
				
			if geo.Geometry.drawModel=='lines' :
				if geo.Geometry.width>1:
					glEnable(GL_POLYGON_OFFSET_FILL)
					glPolygonOffset(-1,1)
				# glLineWidth(3)
				if self.linewidth>geo.Geometry.width:
					glLineWidth(self.linewidth)
				else:
					glLineWidth(geo.Geometry.width)

				glDrawElements(GL_LINES, len(geo.Geometry.index), GL_UNSIGNED_INT,None)
				if geo.Geometry.width>1:
					glDisable(GL_POLYGON_OFFSET_FILL)
			elif geo.Geometry.drawModel=='triangles' :
				glUniform4fv(geo.clipplaneloc,1, self.clipPlane)
				# glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
				glDrawElements(GL_TRIANGLES, 3*len(geo.Geometry.index), GL_UNSIGNED_INT,None)
			elif geo.Geometry.drawModel=='points' :
				glPointSize(self.pointsize)
				glDrawElements(GL_POINTS, len(geo.Geometry.index), GL_UNSIGNED_INT,None)
			else:
				glDrawElements(GL_TRIANGLES, 3*len(geo.Geometry.index), GL_UNSIGNED_INT,None)

			glBindVertexArray(0)
			# glEnable(GL_DEPTH_TEST)

	def setBackgroundColor(self,color):
		self.backGroundColor = color
	def setClip(self,enable=False,clipplane=[0,0,-1,5700.0]):
		self.clipEnable=enable
		self.clipPlane=clipplane
	def animation(self,path='',start=90,output_dir=None):
		"""Render the legacy turntable only beneath an explicit output directory."""
		if output_dir is None:
			raise ValueError("output_dir is required; implicit ../resource/animation writes are disabled")
		base_dir = Path(output_dir).expanduser().resolve()
		relative_path = Path(path) if path else Path()
		if relative_path.is_absolute() or ".." in relative_path.parts:
			raise ValueError("path must stay within the explicit output_dir")
		animation_dir = (base_dir / relative_path).resolve()
		if not animation_dir.is_relative_to(base_dir):
			raise ValueError("animation output escapes output_dir")
		# Loop until the user closes the window
		# tri = FirstTriangle()
		self.__createWindow__(self.size)

		width, height = glfw.get_framebuffer_size(self.window)
		ratio = self.size[0] / float(self.size[1])
		glViewport(0, 0, self.size[0], self.size[1])
		glClearColor(self.backGroundColor[0],self.backGroundColor[1],self.backGroundColor[2],0.0)
		

		self.arcball.mouseEvent = 1
		degreeCount=250
		index=0
		count=int(degreeCount*(start/90+1))
		while not glfw.window_should_close(self.window) and count>index:
			# time.sleep(0.1)
			
			# self.arcball.cursorCallback( self.window, self.size[0]/2+1/3, self.size[1]/2 );
			model = glm.rotate( glm.radians(90/degreeCount), (1,0,0)) 
			self.model=np.matmul(self.model.reshape(4,4),model)
			if index>int(degreeCount*(start/90)):

				self.savepng(os.fspath(animation_dir / ('image'+str(index)+'.png')))
					# Swap front and back buffers

				glfw.swap_buffers(self.window)
				# Poll for and process events
				glfw.poll_events()

			# self.arcball.prevPos = self.arcball.toScreenCoord( self.size[0]/2, self.size[1]/2 )

			index+=1
		self.closeWindow()

	def render_once(self, filename=None):
		"""Create a context, draw one frame, optionally save it, and close."""
		self.__createWindow__(self.size)
		glViewport(0, 0, self.size[0], self.size[1])
		glClearColor(self.backGroundColor[0],self.backGroundColor[1],self.backGroundColor[2],0.0)
		try:
			self.render()
			glFinish()
			if filename is not None:
				self.savepng(filename)
			glfw.swap_buffers(self.window)
			glfw.poll_events()
		finally:
			self.closeWindow()
		return filename

	def run(self):
		# Loop until the user closes the window
		# tri = FirstTriangle()
		self.__createWindow__(self.size)

		width, height = glfw.get_framebuffer_size(self.window)
		ratio = self.size[0] / float(self.size[1])
		glViewport(0, 0, self.size[0], self.size[1])
		glClearColor(self.backGroundColor[0],self.backGroundColor[1],self.backGroundColor[2],0.0)
		
		# glDisable(GL_DEPTH_TEST)
		# glEnable(GL_BLEND)
		# glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
		try:
			while not glfw.window_should_close(self.window):
				self.render()
				glfw.swap_buffers(self.window)
				glfw.poll_events()
		finally:
			self.closeWindow()

	def closeWindow(self):
		window = getattr(self, "window", None)
		if window is not None:
			glfw.destroy_window(window)
			self.window = None
			glfw.terminate()

	def on_key(self,window, key, scancode, action, mods):
		if key == glfw.KEY_ESCAPE and action == glfw.PRESS:
			glfw.set_window_should_close(window,1)
		reset = False
		if key == glfw.KEY_D:
			reset=True
			self.setView('dorsal')
		if key == glfw.KEY_V:
			reset=True
			self.setView('vontral')
		if key == glfw.KEY_L:
			reset=True
			self.setView('left')
		if key == glfw.KEY_R:
			reset=True
			self.setView('right')
		if key == glfw.KEY_A:
			reset=True
			self.setView('anterior')
		if key == glfw.KEY_P:
			reset=True
			self.setView('posterior')		
		if reset:
			self.originModel = glutils.translate(-self.center[0],-self.center[1],-self.center[2])
			self.model = self.originModel
	def on_resize(self,window,w,h):
		self.size=(w,h)
		self.arcball.resize(w,h)
		if h>0:
			glViewport(0, 0, w, h)
			self.projection = glutils.perspective(self.fov, w / float(h),self.near, self.far)
			# self.projection = glutils.ortho(-w*10, w*10, h*10,-h*10, -30000, 30000)
			
		pass
	def define_rotate_angle(self, touch):
		x_angle = (touch.dx/self.width)*360
		y_angle = -1*(touch.dy/self.height)*360
		return x_angle, y_angle
	
	def on_mouse_callback(self,window, xpos, ypos):
		self.arcball.cursorCallback( window, xpos, ypos );
		model = self.arcball.createModelRotationMatrix(self.view)
		if self.arcball.mouseEvent==0:
			return
		self.model=np.matmul(self.originModel.reshape(4,4),model)


	def on_scroll_callback(self,window, xoffset, yoffset):

		if yoffset>0:
			self.fov+=1
		else:
			self.fov-=1
			if self.fov<2:
				self.fov=2

		self.projection = glutils.perspective(self.fov, self.size[0] / float(self.size[1]),self.near, self.far)

		pass
	def on_mouse_button_callback(self,window, button, action, mods):
		self.arcball.mouseButtonCallback( window, button, action, mods );
		if action==glfw.RELEASE and button==glfw.MOUSE_BUTTON_LEFT :
			model = self.arcball.createModelRotationMatrix(self.view)
			self.originModel=np.matmul(self.originModel.reshape(4,4),model)
	def setView(self,type='dorsal'):
		if type=='dorsal':
			self.view=glutils.lookAt(glm.vec3(0.,self.far/10,0.0),glm.vec3(0,0,0),glm.vec3(-1.0,0.0,0.0))
		if type=='vontral':
			self.view=glutils.lookAt(glm.vec3(0.,-self.far/10,0.0),glm.vec3(0,0,0),glm.vec3(-1.0,0.0,0.0))
		if type=='left':
			self.view=glutils.lookAt(glm.vec3(0.,0.0,self.far/10),glm.vec3(0,0,0),glm.vec3(0.0,-1.0,0.0))
		if type=='right':
			self.view=glutils.lookAt(glm.vec3(0.,0.0,-self.far/10),glm.vec3(0,0,0),glm.vec3(0.0,-1.0,0.0))
		if type=='anterior':
			self.view=glutils.lookAt(glm.vec3(-self.far/10.,0.0,0),glm.vec3(0,0,0),glm.vec3(0.0,-1.0,0.0))
		if type=='posterior':
			self.view=glutils.lookAt(glm.vec3(self.far/10.,0.0,-0),glm.vec3(0,0,0),glm.vec3(0.0,-1.0,0.0))
	def setLookAt(self,eye=(0.,0.0,15000),center=(0,0,0),up=(1,0,0)):
		self.view=glutils.lookAt(eye,center,up)

		pass


if __name__ == '__main__':
	raise SystemExit("Use the VisualToolkit brain-view command with an explicit local mesh path.")
