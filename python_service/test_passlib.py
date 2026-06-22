from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

hash = pwd_context.hash("password")
print("Hash:", hash)
valid = pwd_context.verify("password", hash)
print("Verify:", valid)
