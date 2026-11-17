const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const D=require('../docs/data-utils.js');

test('CALLAB equations preserve coefficients and exclude invalid/negative predictions',()=>{
  assert.equal(D.concentration(25,'pm1'),19.29);
  assert.ok(Math.abs(D.concentration(25,'pm01')-3.1)<1e-12);
  assert.equal(D.concentration(2,'pm01'),null);
  for(const value of [null,undefined,NaN,Infinity,-1])assert.equal(D.concentration(value),null);
});
test('particle palettes use the requested limits independently of empirical equations',()=>{
  for(const [name,limits] of Object.entries(D.breaks)){
    limits.forEach((limit,i)=>{
      assert.equal(D.color(limit,name),D.palette[i]);
      assert.equal(D.color(limit+.0001,name),D.palette[i+1]);
    });
  }
  assert.deepEqual(D.breaks.pm1,[12,20,30,60]);
  assert.deepEqual(D.breaks.pm01,[2.25,3.75,5.63,11.25]);
  assert.equal(D.color(null),null);
});
test('Thai date crosses UTC boundary and nearest valid forecast prefers earlier ties',()=>{
  assert.equal(D.thaiDay('2026-11-16T17:00:00Z'),'2026-11-17');
  assert.equal(D.thaiDay('2026-11-16T16:59:59Z'),'2026-11-16');
  const hours=['07','08','09'].map(h=>({status:'Available',valid_time:`2026-11-17T${h}:00:00Z`}));
  assert.equal(D.nearest(hours,'2026-11-17T08:20:00Z'),hours[1]);
  assert.equal(D.nearest([...hours].reverse(),'2026-11-17T08:30:00Z'),hours[1]);
  assert.equal(D.nearest(hours,'2026-11-18T08:00:00Z'),hours[2]);
  assert.equal(D.nearest([{...hours[0],status:'NoData'}]),null);
});
test('automatic priority requires actual MAIAC cells and respects manual choices',()=>{
  assert.equal(D.sourceForDay('auto',{available_cells:1}),'maiac');
  assert.equal(D.sourceForDay('auto',{available_cells:0}),'cams');
  assert.equal(D.sourceForDay('auto',null),'cams');
  assert.equal(D.sourceForDay('cams',{available_cells:99}),'cams');
  assert.equal(D.sourceForDay('maiac',null),'maiac');
});
test('area mean uses clipped overlap, skips missing cells and transforms each concentration',()=>{
  const weights=new Map([['a',1],['b',3],['c',999]]);
  const cells=[['a',0,10],['b',0,30],['c',0,null]];
  assert.equal(D.areaMean(cells,weights),25);
  assert.ok(Math.abs(D.areaMean(cells,weights,'pm1')-19.29)<1e-12);
  assert.equal(D.areaMean([],weights),null);
  assert.equal(D.areaMean([['a',0,1],['b',0,10]],weights,'pm01'),1);
});
test('published real forecast covers 121 consecutive valid hours with a single base',()=>{
  const forecast=JSON.parse(fs.readFileSync('docs/data/cams_forecast.json','utf8'));
  const grid=JSON.parse(fs.readFileSync('docs/data/cams_grid.geojson','utf8'));
  assert.equal(forecast.hours.length,121);
  const weights=new Map(grid.features.map(f=>[f.properties.grid_id,f.properties.overlap_m2]));
  forecast.hours.forEach((h,i)=>{
    assert.equal(Date.parse(h.valid_time),Date.parse(forecast.forecast_base_time)+i*3600000);
    assert.equal(h.forecast_base_time,forecast.forecast_base_time);
    assert.equal(h.cells.length,grid.features.length);
    assert.ok(Math.abs(D.areaMean(h.cells,weights)-h.mean_pm25)<.02);
  });
});
