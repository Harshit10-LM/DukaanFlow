from flask_login import UserMixin
class User(UserMixin):
    def __init__(self, data): self.data=data or {}; self.id=str(self.data.get('_id',''))
    @property
    def email(self): return self.data.get('email','')
    @property
    def business_name(self): return self.data.get('business_name','My Dukaan')
