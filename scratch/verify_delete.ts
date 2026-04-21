async function testDelete() {
  const id = 'market-1776222861569-nea3q7st5';
  console.log(`Testing deletion of ID: ${id}`);
  
  try {
    const response = await fetch(`http://localhost:3000/api/history/${id}`, {
      method: 'DELETE'
    });
    
    const result = await response.json();
    console.log('Response Status:', response.status);
    console.log('Result:', result);
  } catch (err) {
    console.error('Fetch error:', err);
  }
}

testDelete();
