const {test} = require('node:test');
const assert = require('node:assert/strict');
const {interpolate,createSampler} = require('../docs/idw.js');
const triangle = [{x:0,y:0,value:10},{x:1000,y:0,value:30},{x:0,y:1000,value:20}];
test('indexed dense-surface sampler agrees with reference IDW at arbitrary coordinates',()=>{
  const points=Array.from({length:50},(_,i)=>({x:Math.sin(i*3.1)*9000,y:Math.cos(i*1.3)*7000,value:5+i}));
  const targets=Array.from({length:100},(_,i)=>({id:i,x:i*132-6000,y:i*81-4000}));
  const sampler=createSampler(points),reference=interpolate(points,targets);
  reference.values.forEach((v,i)=>{
    const out=sampler(targets[i].x,targets[i].y);
    assert.ok(Math.abs(out.value-v.value)<1e-9);
    assert.ok(Math.abs(out.distance-v.distance)<1e-9);
    assert.equal(out.neighbours,v.neighbours);
  });
  assert.equal(createSampler(triangle)(0,0).value,10);
  assert.equal(createSampler(triangle.slice(0,2)),null);
});
test('IDW preserves source values and gives the expected distance-weighted estimate', () => {
  const out=interpolate(triangle,[{id:'source',x:0,y:0},{id:'middle',x:500,y:500}]);
  assert.equal(out.status,'available');
  assert.equal(out.values[0].value,10);
  assert.equal(out.values[1].value,20);
  assert.equal(out.values[1].neighbours,3);
  assert.ok(Math.abs(out.values[1].distance-Math.sqrt(500000))<1e-8);
});
test('IDW rejects missing, sparse, duplicate and collinear inputs', () => {
  for (const p of [[],triangle.slice(0,2),[triangle[0],triangle[0],triangle[1]],
    [{x:0,y:0,value:1},{x:100,y:100,value:2},{x:200,y:200,value:3}]]) {
    assert.equal(interpolate(p,[{id:'test',x:20,y:30}]).status,'insufficient');
  }
});
test('real history stays bounded, retains original values, and covers only supplied clipped cells', () => {
  const fs=require('node:fs');
  const grid=JSON.parse(fs.readFileSync('docs/data/grid.geojson'));
  const history=JSON.parse(fs.readFileSync('docs/data/history.json'));
  const targets=grid.features.map(f=>({id:f.properties.grid_id,x:f.properties.sample_x,y:f.properties.sample_y}));
  let eligible=0;
  for(const day of history.days){
    const samples=new Map(day.cells.map(c=>[c[0],c[2]]));
    const points=targets.filter(t=>samples.has(t.id)).map(t=>({...t,value:samples.get(t.id)}));
    const out=interpolate(points,targets);
    if(out.status!=='available')continue;
    eligible++;
    assert.equal(out.values.length,grid.features.length);
    const min=Math.min(...points.map(p=>p.value)),max=Math.max(...points.map(p=>p.value));
    out.values.forEach(v=>{
      assert.ok(Number.isFinite(v.value)&&v.value>=min-1e-9&&v.value<=max+1e-9);
      if(samples.has(v.id))assert.equal(v.value,samples.get(v.id));
    });
  }
  assert.ok(eligible>0);
  console.log(`Verified IDW across ${eligible} eligible real dates`);
});
