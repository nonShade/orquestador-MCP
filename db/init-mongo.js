// MongoDB initialization script
db = db.getSiblingDB('ufro_master');

// Create collections
db.createCollection('access_logs');
db.createCollection('service_logs'); 
db.createCollection('users');
db.createCollection('config');

console.log('Database ufro_master initialized with collections');