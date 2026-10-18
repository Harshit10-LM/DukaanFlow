from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient, ASCENDING
from werkzeug.security import generate_password_hash

def now(): return datetime.now(timezone.utc)
class Repository:
    def __init__(self,cfg):
        self.demo=not bool(cfg.get('MONGODB_URI')); self.status='demo (records reset on restart)' if self.demo else 'connected'
        self.data={'users':{},'products':{},'orders':{}}
        if self.demo:
            self.seed()
        else:
            self.client=MongoClient(cfg['MONGODB_URI'],serverSelectionTimeoutMS=3000); self.client.admin.command('ping'); self.db=self.client[cfg['MONGODB_DB']]
            self.db.users.create_index('email',unique=True); self.db.products.create_index([('user_id',ASCENDING),('name',ASCENDING)]); self.db.orders.create_index([('user_id',ASCENDING),('created_at',-1)])
    def oid(self,v):
        try:return ObjectId(v)
        except:return None
    def seed(self):
        uid=str(ObjectId()); self.data['users'][uid]={'_id':uid,'email':'demo@dukaanflow.test','password':generate_password_hash('DemoPass123'),'business_name':'Meera Studio','created_at':now()}
        for name,price,cost in [('Navy Kurti',650,340),('Cotton Scarf',399,185)]: self.create_product(uid,{'name':name,'selling_price':str(price),'unit_cost':str(cost),'packaging_cost':'20','stock':'12'})
    def get_user(self,uid):
        if self.demo:return self.data['users'].get(str(uid))
        oid=self.oid(uid); return self.db.users.find_one({'_id':oid}) if oid else None
    def by_email(self,email):
        if self.demo:return next((u for u in self.data['users'].values() if u['email']==email.lower()),None)
        return self.db.users.find_one({'email':email.lower()})
    def create_user(self,email,password,business_name):
        d={'email':email.lower(),'password':generate_password_hash(password),'business_name':business_name,'created_at':now()}
        if self.demo: d['_id']=str(ObjectId());self.data['users'][d['_id']]=d
        else: d['_id']=self.db.users.insert_one(d).inserted_id
        return d
    def _coll(self,name): return self.data[name] if self.demo else self.db[name]
    def create_product(self,uid,d):
        d={**d,'user_id':str(uid),'created_at':now(),'updated_at':now()}; d['_id']=str(ObjectId()) if self.demo else self.db.products.insert_one(d).inserted_id
        if self.demo:self.data['products'][str(d['_id'])]=d
        return d
    def list_products(self,uid,q=''):
        if self.demo:return [x for x in self.data['products'].values() if x['user_id']==str(uid) and q.lower() in x['name'].lower()]
        filt={'user_id':str(uid)}; 
        if q:filt['name']={'$regex':q,'$options':'i'}
        return list(self.db.products.find(filt).sort('name',1))
    def get_product(self,uid,id):
        if self.demo:
            x=self.data['products'].get(id); return x if x and x['user_id']==str(uid) else None
        oid=self.oid(id);return self.db.products.find_one({'_id':oid,'user_id':str(uid)}) if oid else None
    def update_product(self,uid,id,d):
        x=self.get_product(uid,id)
        if not x:return None
        d={**d,'updated_at':now()}
        if self.demo:x.update(d);return x
        self.db.products.update_one({'_id':x['_id'],'user_id':str(uid)},{'$set':d});return self.get_product(uid,id)
    def delete_product(self,uid,id):
        x=self.get_product(uid,id)
        if not x:return False
        if self.demo:del self.data['products'][id]
        else:self.db.products.delete_one({'_id':x['_id'],'user_id':str(uid)})
        return True
    @staticmethod
    def _normalize_order(order):
        if not order: return None
        items = order.get('items')
        if not isinstance(items, list):
            single = order.get('item')
            items = [single] if isinstance(single, dict) else []
            order['items'] = items
        for item in items:
            if not isinstance(item, dict): continue
            item.setdefault('name', '')
            item.setdefault('variant', '')
            item.setdefault('quantity', 1)
            item.setdefault('selling_price', '0.00')
            item.setdefault('unit_cost', '')
            item.setdefault('packaging_cost', '0.00')
        order.setdefault('calculation', {})
        order.setdefault('other_cost', '0.00')
        order.setdefault('status', 'Draft')
        order.setdefault('delivery_date', order.get('delivery_request_text', ''))
        return order
    def create_order(self,uid,d):
        d={**d,'user_id':str(uid),'created_at':now(),'updated_at':now()}; d['_id']=str(ObjectId()) if self.demo else self.db.orders.insert_one(d).inserted_id
        if self.demo:self.data['orders'][str(d['_id'])]=d
        return self._normalize_order(d)
    def list_orders(self,uid,q='',status=''):
        if self.demo:
            raw = [x for x in self.data['orders'].values() if x['user_id']==str(uid) and (not q or q.lower() in x.get('customer_name','').lower()) and (not status or x.get('status')==status)]
            return [self._normalize_order(o) for o in raw]
        f={'user_id':str(uid)};
        if q:f['customer_name']={'$regex':q,'$options':'i'}
        if status:f['status']=status
        raw = list(self.db.orders.find(f).sort('created_at',-1))
        return [self._normalize_order(o) for o in raw]
    def get_order(self,uid,id):
        if self.demo:
            x=self.data['orders'].get(id);return self._normalize_order(x) if x and x['user_id']==str(uid) else None
        oid=self.oid(id); doc=self.db.orders.find_one({'_id':oid,'user_id':str(uid)}) if oid else None
        return self._normalize_order(doc)
    def update_order(self,uid,id,d):
        x=self.get_order(uid,id)
        if not x:return None
        d={**d,'updated_at':now()}
        if self.demo:x.update(d);return self._normalize_order(x)
        self.db.orders.update_one({'_id':x['_id'],'user_id':str(uid)},{'$set':d});return self.get_order(uid,id)

