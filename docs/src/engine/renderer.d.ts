export interface GlassPanel { x:number;y:number;halfWidth:number;halfHeight:number;radius:number;clip?:{x:number;y:number;width:number;height:number}; }
export interface View {pan:{x:number;y:number};panels:GlassPanel[];glassLength:number;}
export function createRenderer(canvas:HTMLCanvasElement,lightness:number):{draw:(now:number,view:View)=>void;interval:number;themeColor:string;dispose:()=>void};
