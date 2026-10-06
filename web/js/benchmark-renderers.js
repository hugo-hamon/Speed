// Deux consommateurs de la même liste de rectangles texturés, dans le même ordre.
export class CanvasBackend {
  constructor(canvas){this.canvas=canvas;this.ctx=canvas.getContext('2d',{alpha:false});}
  draw(commands){const c=this.ctx;c.setTransform(1,0,0,1,0,0);c.fillStyle='#edf2e7';c.fillRect(0,0,this.canvas.width,this.canvas.height);for(const q of commands)c.drawImage(q.image,q.sx,q.sy,q.sw,q.sh,q.x,q.y,q.w,q.h);}
  dispose(){}
}
export class WebGLBackend {
  constructor(canvas){
    this.canvas=canvas;this.gl=canvas.getContext('webgl',{alpha:false,antialias:false,powerPreference:'high-performance'});
    if(!this.gl)throw new Error('WebGL indisponible : le comparatif ne peut pas être exécuté.');
    const gl=this.gl;this.textures=new Map();this.vertices=new Float32Array(6*4*4096);
    const shader=(type,code)=>{const s=gl.createShader(type);gl.shaderSource(s,code);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;};
    const vs=shader(gl.VERTEX_SHADER,'attribute vec2 position; attribute vec2 uv; uniform vec2 resolution; varying vec2 texcoord; void main(){gl_Position=vec4(position/resolution*vec2(2.,-2.)+vec2(-1.,1.),0.,1.);texcoord=uv;}');
    const fs=shader(gl.FRAGMENT_SHADER,'precision mediump float; varying vec2 texcoord; uniform sampler2D image; void main(){gl_FragColor=texture2D(image,texcoord);}');
    this.program=gl.createProgram();gl.attachShader(this.program,vs);gl.attachShader(this.program,fs);gl.linkProgram(this.program);gl.deleteShader(vs);gl.deleteShader(fs);
    if(!gl.getProgramParameter(this.program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(this.program));
    gl.useProgram(this.program);this.buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);gl.bufferData(gl.ARRAY_BUFFER,this.vertices.byteLength,gl.DYNAMIC_DRAW);
    for(const [name,offset] of [['position',0],['uv',8]]){const location=gl.getAttribLocation(this.program,name);gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,2,gl.FLOAT,false,16,offset);}
    this.resolution=gl.getUniformLocation(this.program,'resolution');gl.uniform1i(gl.getUniformLocation(this.program,'image'),0);
    gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);
    const debug=gl.getExtension('WEBGL_debug_renderer_info');
    this.info={version:gl.getParameter(gl.VERSION),renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),vendor:debug?gl.getParameter(debug.UNMASKED_VENDOR_WEBGL):gl.getParameter(gl.VENDOR),maxTextureSize:gl.getParameter(gl.MAX_TEXTURE_SIZE)};
  }
  upload(image){const gl=this.gl;const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);this.textures.set(image,texture);}
  draw(commands){
    const gl=this.gl;gl.viewport(0,0,this.canvas.width,this.canvas.height);gl.uniform2f(this.resolution,this.canvas.width,this.canvas.height);gl.clearColor(237/255,242/255,231/255,1);gl.clear(gl.COLOR_BUFFER_BIT);
    let image=null,count=0;
    const flush=()=>{if(!count)return;gl.bindTexture(gl.TEXTURE_2D,this.textures.get(image));gl.bufferSubData(gl.ARRAY_BUFFER,0,this.vertices.subarray(0,count));gl.drawArrays(gl.TRIANGLES,0,count/4);count=0;};
    for(const q of commands){
      if(q.image!==image||count+24>this.vertices.length){flush();image=q.image;}
      const l=q.x,r=q.x+q.w,t=q.y,b=q.y+q.h,u=q.sx/q.image.width,v=q.sy/q.image.height,ur=(q.sx+q.sw)/q.image.width,vb=(q.sy+q.sh)/q.image.height;
      this.vertices.set([l,t,u,v,r,t,ur,v,l,b,u,vb,l,b,u,vb,r,t,ur,v,r,b,ur,vb],count);count+=24;
    }
    flush();
  }
  dispose(){const gl=this.gl;for(const texture of this.textures.values())gl.deleteTexture(texture);this.textures.clear();gl.deleteBuffer(this.buffer);gl.deleteProgram(this.program);gl.getExtension('WEBGL_lose_context')?.loseContext();}
}
