// Optional integration check: PUPPETEER_MODULE=/absolute/path/to/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js node validation/browser.mjs
import fs from 'node:fs'
const { default: puppeteer } = await import(process.env.PUPPETEER_MODULE || 'puppeteer-core')
const browser=await puppeteer.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/chromium',args:['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader'],defaultViewport:{width:1440,height:900},protocolTimeout:180000})
const page=await browser.newPage(), errors=[], timings=[]
page.on('pageerror',e=>errors.push(e.message))
try {
 await page.goto(process.env.NETSY_VIZ_URL || 'http://127.0.0.1:5175/',{waitUntil:'networkidle0'})
 await page.evaluate(async()=>{ const {parseCsv}=await import('/src/loaders.ts'); const t=parseCsv('zone_id,quantity\n001,2\n'); if(t.rows[0].zone_id!=='001'||t.rows[0].quantity!==2) throw Error('CSV identifier preservation failed') })
 await page.evaluate(()=>[...document.querySelectorAll('.bubble')].find(e=>e.textContent==='Data'&&!e.closest('[inert]')).click())
 for(const name of ['network.gpkg','network_loads.parquet']){
  const start=Date.now()
  const [chooser]=await Promise.all([page.waitForFileChooser(),page.evaluate(name=>[...document.querySelectorAll('.file')].find(e=>e.getAttribute('aria-label').endsWith(`(${name})`)).click(),name)])
  await chooser.accept([`/workdir/netherlands/${name}`])
  await page.waitForSelector('.loading',{hidden:true,timeout:180000})
  const error=await page.$eval('.error',e=>e.textContent).catch(()=>null)
  if(error)throw Error(error)
  timings.push({name,milliseconds:Date.now()-start})
 }
 const tableStart=Date.now()
 await page.evaluate(()=>[...document.querySelectorAll('.file')].find(e=>e.getAttribute('aria-label').endsWith('(network_loads.parquet)')).click())
 await page.waitForFunction(()=>document.querySelector('.table-view .paper')?.getAttribute('aria-label')?.includes('rows'))
 const tableOpenMilliseconds=Date.now()-tableStart
 const rowLabel=await page.$eval('.table-view .paper',e=>e.getAttribute('aria-label'))
 await page.screenshot({path:'/workdir/netsy/validation/results/visualizer-table.png'})
 await page.evaluate(()=>[...document.querySelectorAll('.bubble')].find(e=>e.textContent==='Data'&&!e.closest('[inert]')).click())
 await page.evaluate(()=>[...document.querySelectorAll('.bubble')].find(e=>e.textContent==='Map'&&!e.closest('[inert]')).click())
 await page.select('.controls select','loads')
 await page.waitForFunction(()=>document.querySelector('.legend-ticks')?.textContent?.length>0)
 await page.screenshot({path:'/workdir/netsy/validation/results/visualizer-loads.png'})
 if(errors.length)throw Error(errors.join('; '))
 fs.writeFileSync('/workdir/netsy/validation/results/browser.json',JSON.stringify({timings,rowLabel,tableOpenMilliseconds,errors},null,2))
 console.log(JSON.stringify({timings,rowLabel,tableOpenMilliseconds,errors}))
} finally {await browser.close()}
