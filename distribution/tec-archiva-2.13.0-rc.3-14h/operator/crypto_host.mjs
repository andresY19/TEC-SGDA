import {generateKeyPairSync, sign, verify} from 'node:crypto';

let raw='';
for await (const chunk of process.stdin) raw+=chunk;
const input=JSON.parse(raw);
if(input.action==='generate'){
  const pair=generateKeyPairSync('ed25519');
  console.log(JSON.stringify({
    private_key:pair.privateKey.export({type:'pkcs8',format:'pem'}),
    public_key:pair.publicKey.export({type:'spki',format:'pem'})
  }));
}else if(input.action==='sign'){
  console.log(JSON.stringify({signature:sign(null,Buffer.from(input.message,'base64'),input.private_key).toString('base64')}));
}else if(input.action==='verify'){
  console.log(JSON.stringify({valid:verify(null,Buffer.from(input.message,'base64'),input.public_key,Buffer.from(input.signature,'base64'))}));
}else{
  process.exitCode=1;
}
